#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///

"""
XID Error Analyzer — Python port of NVSentinel's XID parsing logic.

Parses syslog/journald logs for NVIDIA XID errors. Uses generated JSON catalog
data for error resolution mapping.

XID_CATALOG_URL = https://docs.nvidia.com/deploy/xid-errors/_downloads/4586dadb59119a55d1e93a181caa4272/Xid-Catalog.xlsx

Usage:
    uv run xid_checker.py --log /var/log/syslog
    uv run xid_checker.py --log /var/log/syslog --catalog ./Xid-Catalog.xlsx
    python3 xid_checker.py --generate-catalog-data xid_catalog_data.json
    python3 xid_checker.py --generate-catalog-data xid_catalog_data.json --catalog ./Xid-Catalog.xlsx
    python3 xid_checker.py --log /var/log/syslog --driver-version 570.148.08
    journalctl -k | uv run xid_checker.py --log -
"""

import argparse
import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RecommendedAction
# ---------------------------------------------------------------------------
class RecommendedAction(str, Enum):
    NONE = "none"
    WARNING = "warning"
    CRITICAL = "critical"
    GPU_RESET_REBOOT = "gpu_reset_reboot"


XID_CATALOG_URL = (
    "https://docs.nvidia.com/deploy/xid-errors/_downloads/"
    "4586dadb59119a55d1e93a181caa4272/Xid-Catalog.xlsx"
)
DEFAULT_CATALOG_JSON = "xid_catalog_data.json"

# ---------------------------------------------------------------------------
# Action-string → RecommendedAction mapping
# ---------------------------------------------------------------------------
_PROTO_ENUM_NAMES = {e.name.upper(): e for e in RecommendedAction}

_SPECIAL_MAP = {
    # Old enum names from XLSX catalog
    "COMPONENT_RESET": RecommendedAction.GPU_RESET_REBOOT,
    "CONTACT_SUPPORT": RecommendedAction.CRITICAL,
    "RUN_FIELDDIAG": RecommendedAction.WARNING,
    "RESTART_VM": RecommendedAction.GPU_RESET_REBOOT,
    "RESTART_BM": RecommendedAction.GPU_RESET_REBOOT,
    "REPLACE_VM": RecommendedAction.GPU_RESET_REBOOT,
    "RUN_DCGMEUD": RecommendedAction.WARNING,
    "CUSTOM": RecommendedAction.WARNING,
    "UNKNOWN": RecommendedAction.CRITICAL,
    # Special action strings
    "RESTART_APP": RecommendedAction.WARNING,
    "IGNORE": RecommendedAction.WARNING,
    "XID_154_EVAL": RecommendedAction.WARNING,
    "XID_154": RecommendedAction.WARNING,
    "WORKFLOW_XID_45": RecommendedAction.CRITICAL,
    "WORKFLOW_XID_48": RecommendedAction.GPU_RESET_REBOOT,
    "WORKFLOW_NVLINK_ERR": RecommendedAction.CRITICAL,
    "WORKFLOW_NVLINK5_ERR": RecommendedAction.CRITICAL,
    "CHECK_MECHANICALS": RecommendedAction.CRITICAL,
    "CHECK_UVM": RecommendedAction.GPU_RESET_REBOOT,
    "UPDATE_SWFW": RecommendedAction.CRITICAL,
    "RESET_GPU": RecommendedAction.GPU_RESET_REBOOT,
    "RESET_FABRIC": RecommendedAction.GPU_RESET_REBOOT,
}

ACTION_MAP = {**_PROTO_ENUM_NAMES, **_SPECIAL_MAP}


def map_action_string(action_str: str, source: str = "") -> RecommendedAction:
    key = action_str.strip().upper()
    if key in ACTION_MAP:
        return ACTION_MAP[key]
    loc = f" ({source})" if source else ""
    log.warning("Unknown action string, defaulting to CRITICAL: %s%s", action_str, loc)
    return RecommendedAction.CRITICAL


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
XID_PATTERN = re.compile(
    r"NVRM: Xid \(PCI:([0-9a-fA-F:.]+)\): (\d+)"
    r"(?:, pid=(\d+))?(?:, name=([^,]+))?(?:, Ch ([0-9a-fA-F]+))?"
)

NVL5_XID_PATTERN = re.compile(
    r"NVRM: Xid \(PCI:([^)]+)\): (\d+)"
    r"(?:, pid=[^,]*)?(?:, name=[^,]*)?, "
    r"(\w+)\s+(\w+)\s+(\w+)\s+(\w+)\s+"
    r"Link\s+(-?\d+)\s+\((0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)"
)

NVRM_GPU_MAP_PATTERN = re.compile(
    r"NVRM: GPU at PCI:([0-9a-fA-F:.]+): (GPU-[0-9a-fA-F-]+)"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class NVL5DecodingRule:
    xid_number: int
    intr_info_binary: str
    error_status_hex: list[str] = field(default_factory=list)
    resolution: str = ""
    mnemonic: str = ""
    _intrinfo_mask: int = 0
    _intrinfo_value: int = 0

    def __post_init__(self):
        self._intrinfo_mask, self._intrinfo_value = _compile_intrinfo_pattern(
            self.intr_info_binary
        )


@dataclass
class ErrorResolution:
    recommended_action: RecommendedAction = RecommendedAction.CRITICAL
    description: str = ""


@dataclass
class XIDEvent:
    xid_code: int
    decoded_xid_str: str
    pci_address: str
    gpu_uuid: str | None
    is_fatal: bool
    severity: str
    recommended_action: RecommendedAction
    recommended_action_name: str
    message: str
    description: str = ""
    entities: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stdlib XLSX catalog conversion
# ---------------------------------------------------------------------------
_XLSX_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_XLSX_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_XLSX_PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _xlsx_tag(name: str) -> str:
    return f"{{{_XLSX_MAIN_NS}}}{name}"


def _column_index(cell_ref: str) -> int:
    """Return a zero-based column index from an Excel cell reference."""
    col = 0
    for ch in cell_ref:
        if not ch.isalpha():
            break
        col = col * 26 + (ord(ch.upper()) - ord("A") + 1)
    return col - 1


def _read_shared_strings(workbook_zip: zipfile.ZipFile) -> list[str]:
    try:
        data = workbook_zip.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ET.fromstring(data)
    strings = []
    for si in root.findall(_xlsx_tag("si")):
        parts = [t.text or "" for t in si.iter(_xlsx_tag("t"))]
        strings.append("".join(parts))
    return strings


def _cell_value(
    cell: ET.Element, shared_strings: list[str]
) -> str | int | float | None:
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        parts = [t.text or "" for t in cell.iter(_xlsx_tag("t"))]
        return "".join(parts)

    value = cell.find(_xlsx_tag("v"))
    if value is None or value.text is None:
        return None

    raw = value.text
    if cell_type == "s":
        try:
            return shared_strings[int(raw)]
        except (IndexError, ValueError):
            return raw
    if cell_type in {"str", "b"}:
        return raw

    try:
        number = float(raw)
    except ValueError:
        return raw
    if number.is_integer():
        return int(number)
    return number


def _worksheet_path_for_sheet(workbook_zip: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(workbook_zip.read("xl/workbook.xml"))
    rels = ET.fromstring(workbook_zip.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall(f"{{{_XLSX_PACKAGE_REL_NS}}}Relationship")
    }

    sheets = workbook.find(_xlsx_tag("sheets"))
    if sheets is None:
        raise ValueError("workbook has no sheets")

    for sheet in sheets.findall(_xlsx_tag("sheet")):
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib.get(f"{{{_XLSX_REL_NS}}}id")
        target = rel_map.get(rel_id or "")
        if not target:
            raise ValueError(f"worksheet relationship not found for {sheet_name!r}")
        if target.startswith("/"):
            return target.lstrip("/")
        if target.startswith("xl/"):
            return target
        return f"xl/{target}"

    raise ValueError(f"sheet not found: {sheet_name}")


def _read_xlsx_sheet_rows(catalog_path: str | Path, sheet_name: str) -> list[list]:
    """Read worksheet rows from an XLSX file using only Python's standard library."""
    with zipfile.ZipFile(catalog_path) as workbook_zip:
        shared_strings = _read_shared_strings(workbook_zip)
        worksheet_path = _worksheet_path_for_sheet(workbook_zip, sheet_name)
        worksheet = ET.fromstring(workbook_zip.read(worksheet_path))

    rows = []
    sheet_data = worksheet.find(_xlsx_tag("sheetData"))
    if sheet_data is None:
        return rows

    for row in sheet_data.findall(_xlsx_tag("row")):
        values = []
        for cell in row.findall(_xlsx_tag("c")):
            ref = cell.attrib.get("r", "")
            col_idx = _column_index(ref)
            if col_idx < 0:
                continue
            if len(values) <= col_idx:
                values.extend([None] * (col_idx - len(values) + 1))
            values[col_idx] = _cell_value(cell, shared_strings)
        rows.append(values)
    return rows


def _catalog_data_from_xlsx(
    catalog_path: str | Path,
) -> tuple[dict[int, dict[str, str]], dict[int, list[dict]]]:
    error_catalog: dict[int, dict[str, str]] = {}
    for i, row in enumerate(_read_xlsx_sheet_rows(catalog_path, "Xids")):
        if i == 0:
            continue
        cells = list(row) + [None] * (9 - len(row))
        code_str = cells[1] or ""
        action_str = cells[8] or ""
        description = cells[3] or ""
        if not code_str:
            continue
        try:
            code = int(code_str)
        except (ValueError, TypeError):
            continue
        error_catalog[code] = {
            "description": str(description).strip(),
            "action": str(action_str).strip(),
        }

    nvl5_rules: dict[int, list[dict]] = {}
    for i, row in enumerate(_read_xlsx_sheet_rows(catalog_path, "Xid 144-150 Decode")):
        if i == 0:
            continue
        cells = list(row) + [None] * (11 - len(row))
        xid_str = cells[0] or ""
        if not str(xid_str).strip():
            continue
        try:
            xid_code = int(xid_str)
        except (ValueError, TypeError):
            continue
        error_status_raw = cells[4] or ""
        nvl5_rules.setdefault(xid_code, []).append(
            {
                "mnemonic": str(cells[1] or "").strip(),
                "intr_info_binary_pre_r575": str(cells[2] or "").strip(),
                "intr_info_binary_r575": str(cells[3] or "").strip(),
                "error_status_hex": [
                    s.strip() for s in str(error_status_raw).split("/") if s.strip()
                ],
                "resolution": str(cells[5] or "").strip(),
            }
        )

    return error_catalog, nvl5_rules


def generate_xid_catalog_data(
    catalog_path: str | Path = "Xid-Catalog.xlsx",
    output_path: str | Path = DEFAULT_CATALOG_JSON,
) -> Path:
    """Convert Xid-Catalog.xlsx to a stdlib-only JSON data file."""
    error_catalog, nvl5_rules = _catalog_data_from_xlsx(catalog_path)
    catalog_md5 = hashlib.md5(Path(catalog_path).read_bytes()).hexdigest()
    output = Path(output_path)
    catalog_data = {
        "metadata": {
            "source": Path(catalog_path).name,
            "source_md5": catalog_md5,
            "generated_by": "xid_checker.generate_xid_catalog_data()",
        },
        "xid_error_catalog": error_catalog,
        "nvl5_decoding_rules": nvl5_rules,
    }
    output.write_text(
        json.dumps(catalog_data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def _catalog_data_from_json(
    catalog_path: str | Path,
) -> tuple[dict[int, dict[str, str]], dict[int, list[dict]]]:
    """Load generated JSON catalog data and restore integer XID keys."""
    with Path(catalog_path).open(encoding="utf-8") as f:
        catalog_data = json.load(f)

    try:
        raw_error_catalog = catalog_data["xid_error_catalog"]
        raw_nvl5_rules = catalog_data["nvl5_decoding_rules"]
    except KeyError as exc:
        raise ValueError(f"Invalid XID catalog JSON: missing {exc.args[0]}") from exc

    error_catalog = {
        int(code): entry for code, entry in raw_error_catalog.items()
    }
    nvl5_rules = {
        int(xid_code): rules for xid_code, rules in raw_nvl5_rules.items()
    }
    return error_catalog, nvl5_rules


def _catalog_data_from_path(
    catalog_path: str | Path,
) -> tuple[dict[int, dict[str, str]], dict[int, list[dict]]]:
    path = Path(catalog_path)
    if path.suffix.lower() == ".json":
        return _catalog_data_from_json(path)
    return _catalog_data_from_xlsx(path)


# ---------------------------------------------------------------------------
# XID Catalog Loader
# ---------------------------------------------------------------------------


class XIDCatalog:
    """Loads and serves the NVIDIA XID Error Catalog from XLSX or generated JSON."""

    # Hardcoded overrides — take precedence over XLSX catalog values.
    _XID_OVERRIDES: dict[int, RecommendedAction] = {
        74: RecommendedAction.GPU_RESET_REBOOT,
        **{
            x: RecommendedAction.WARNING
            for x in (
                45,
                73,
                74,
                78,
                81,
                87,
                90,
                91,
                *range(111, 119),  # 111-118
                *range(122, 126),  # 122-125
                138,
                142,
            )
        },
    }

    def __init__(self, catalog_path: str | None = None, driver_version: str = ""):
        self.driver_version = driver_version
        self.error_resolution_map: dict[int, ErrorResolution] = {}
        self.error_descriptions: dict[int, str] = {}
        self.error_action_strings: dict[int, str] = {}
        self.nvl5_rules: dict[int, list[NVL5DecodingRule]] = {}

        if catalog_path:
            error_catalog, nvl5_rules = _catalog_data_from_path(catalog_path)
        else:
            default_catalog = Path(__file__).resolve().parent / DEFAULT_CATALOG_JSON
            if not default_catalog.exists():
                raise FileNotFoundError(
                    f"{DEFAULT_CATALOG_JSON} not found. Run "
                    f"python3 xid_checker.py --generate-catalog-data {DEFAULT_CATALOG_JSON} "
                    "to create the JSON catalog data file."
                )
            error_catalog, nvl5_rules = _catalog_data_from_json(default_catalog)

        self._load_xid_catalog(error_catalog)
        self._load_nvl5_rules(nvl5_rules)

        log.debug(
            "Loaded %d XID error resolution mappings", len(self.error_resolution_map)
        )
        log.debug("Loaded NVL5 rules for %d XID types", len(self.nvl5_rules))

    def _load_xid_catalog(self, error_catalog: dict[int, dict[str, str]]):
        self.error_descriptions = {
            code: str(entry.get("description", ""))
            for code, entry in error_catalog.items()
        }
        for code, entry in error_catalog.items():
            action_str = str(entry.get("action", "")).strip()
            self.error_action_strings[code] = action_str
            if not action_str:
                continue
            self.error_resolution_map[code] = ErrorResolution(
                recommended_action=map_action_string(
                    str(action_str), source=f"Xids data, XID {code}"
                ),
                description=self.error_descriptions.get(code, ""),
            )

    def _load_nvl5_rules(self, nvl5_rules: dict[int, list[dict]]):
        for xid_code, rules in nvl5_rules.items():
            for raw_rule in rules:
                if self._is_driver_r575_or_newer():
                    intr_info = raw_rule.get("intr_info_binary_r575", "")
                else:
                    intr_info = raw_rule.get("intr_info_binary_pre_r575", "")

                rule = NVL5DecodingRule(
                    xid_number=xid_code,
                    intr_info_binary=str(intr_info).strip(),
                    error_status_hex=list(raw_rule.get("error_status_hex", [])),
                    resolution=str(raw_rule.get("resolution", "")).strip(),
                    mnemonic=str(raw_rule.get("mnemonic", "")).strip(),
                )
                self.nvl5_rules.setdefault(xid_code, []).append(rule)

    def _is_driver_r575_or_newer(self) -> bool:
        if not self.driver_version:
            return True
        parts = self.driver_version.split(".", 1)
        if not parts:
            return True
        try:
            return int(parts[0]) >= 575
        except ValueError:
            return True

    def _is_unused_xid(self, xid_code: int) -> bool:
        return self.get_description(xid_code).strip() == "Unused"

    def _requires_nvl5_decode(self, xid_code: int) -> bool:
        action_str = self.error_action_strings.get(xid_code, "").strip().upper()
        return (
            action_str == "WORKFLOW_NVLINK5_ERR"
            and xid_code in self.nvl5_rules
        )

    def get_action(self, xid_code: int) -> RecommendedAction:
        if self._is_unused_xid(xid_code):
            return RecommendedAction.WARNING
        if self._requires_nvl5_decode(xid_code):
            # Catalog action means "decode by NVL5 subcode first", not "treat as CRITICAL".
            return RecommendedAction.NONE
        if xid_code in self._XID_OVERRIDES:
            return self._XID_OVERRIDES[xid_code]
        if xid_code in self.error_resolution_map:
            return self.error_resolution_map[xid_code].recommended_action
        return RecommendedAction.CRITICAL

    def get_description(self, xid_code: int) -> str:
        if xid_code in self.error_descriptions:
            return self.error_descriptions[xid_code]
        return f"XID {xid_code}"

    def lookup(self, xid_code: int) -> dict:
        """Look up a single XID code and return its resolution info.

        Returns dict with keys: xid_code, recommended_action, recommended_action_name.
        For XIDs 144-150, also returns matching NVL5 rules.
        """
        action = self.get_action(xid_code)
        result = {
            "xid_code": xid_code,
            "description": self.get_description(xid_code),
            "recommended_action": action,
            "recommended_action_name": action.name,
        }
        if self._requires_nvl5_decode(xid_code):
            result["requires_nvl5_decode"] = True
        if xid_code in self.nvl5_rules:
            result["nvl5_rules"] = [
                {
                    "mnemonic": r.mnemonic,
                    "intr_info_binary": r.intr_info_binary,
                    "error_status_hex": r.error_status_hex,
                    "resolution": r.resolution,
                }
                for r in self.nvl5_rules[xid_code]
            ]
        return result


# ---------------------------------------------------------------------------
# NVL5 IntrInfo binary matching
# ---------------------------------------------------------------------------
def _compile_intrinfo_pattern(pattern: str) -> tuple[int, int]:
    """Pre-compile a binary pattern into (mask, value) integers.

    Pattern uses '-' as wildcard (don't-care), '0'/'1' as exact match.
    Returns a (mask, value) pair where mask has 1-bits for positions that
    must match and value has the expected bits. Both are right-aligned.
    """
    mask = 0
    value = 0
    for ch in pattern:
        mask <<= 1
        value <<= 1
        if ch == "1":
            mask |= 1
            value |= 1
        elif ch == "0":
            mask |= 1
        # '-' → mask bit stays 0, value bit stays 0
    return mask, value


def _intrinfo_matches(mask: int, value: int, intr_info_int: int) -> bool:
    """Test whether intr_info_int matches the pre-compiled (mask, value) pair."""
    return (intr_info_int & mask) == value


def matches_nvl5_rule(
    rule: NVL5DecodingRule, intr_info_int: int, error_status_str: str
) -> bool:
    """Match an NVL5 decoding rule."""
    # ErrorStatus matching
    found_match = False
    all_empty = True
    for e in rule.error_status_hex:
        if not e:
            continue
        all_empty = False
        if e == error_status_str:
            found_match = True
            break

    if not all_empty and not found_match:
        return False

    return _intrinfo_matches(rule._intrinfo_mask, rule._intrinfo_value, intr_info_int)


# ---------------------------------------------------------------------------
# XID Processor
# ---------------------------------------------------------------------------
class XIDProcessor:
    def __init__(self, catalog: XIDCatalog):
        self.catalog = catalog
        self.pci_to_gpu_dmesg: dict[str, str] = {}  # populated from NVRM mapping lines

        self.xid_events: list[XIDEvent] = []

    @staticmethod
    def _normalize_pci_handler(pci: str) -> str:
        """XID handler's PCI normalization — strips function number after '.'."""
        dot_idx = pci.find(".")
        if dot_idx != -1:
            return pci[:dot_idx]
        return pci

    def _get_gpu_uuid(self, norm_pci: str) -> str | None:
        """Resolve GPU UUID from dmesg-derived map."""
        return self.pci_to_gpu_dmesg.get(norm_pci)

    def _determine_fatality(self, action: RecommendedAction) -> bool:
        return action not in (RecommendedAction.NONE, RecommendedAction.WARNING)

    def process_line(self, message: str):
        """Process a single syslog line. Mirrors XIDHandler.ProcessLine."""
        # 1. Check for PCI→GPU UUID mapping line
        m = NVRM_GPU_MAP_PATTERN.search(message)
        if m:
            pci_raw, gpu_uuid = m.group(1), m.group(2)
            norm_pci = self._normalize_pci_handler(pci_raw)
            self.pci_to_gpu_dmesg[norm_pci] = gpu_uuid
            return

        # 2. Try NVL5 parse first, then standard
        resp = self._parse_nvl5_xid(message)
        if resp is None:
            resp = self._parse_standard_xid(message)

        if resp is None:
            return

        self._create_health_event(resp, message)

    def _parse_nvl5_xid(self, message: str) -> dict | None:
        """Try to parse an NVL5 XID (144-150). Returns parsed dict or None."""
        m = NVL5_XID_PATTERN.search(message)
        if not m:
            return None

        pci_addr = m.group(1)
        xid_code = int(m.group(2))
        subcode = m.group(3)
        # severity = m.group(4)  # e.g. "Nonfatal"
        # crosscontain = m.group(5)
        # injected = m.group(6)
        # link_num = m.group(7)
        intr_info = int(m.group(8), 16)
        error_status_str = m.group(9)

        rules = self.catalog.nvl5_rules.get(xid_code)
        if not rules:
            return None

        recommended_action = RecommendedAction.NONE
        rule_mnemonic = ""

        for rule in rules:
            if matches_nvl5_rule(rule, intr_info, error_status_str):
                recommended_action = map_action_string(
                    rule.resolution,
                    source=f"NVL5 sheet, XID {xid_code} subcode {rule.mnemonic}",
                )
                rule_mnemonic = rule.mnemonic
                break

        decoded_xid_str = f"{xid_code}.{subcode}"

        return {
            "decoded_xid_str": decoded_xid_str,
            "xid_code": xid_code,
            "pci": pci_addr,
            "description": self.catalog.get_description(xid_code),
            "recommended_action": recommended_action,
            "mnemonic": rule_mnemonic,
        }

    def _parse_standard_xid(self, message: str) -> dict | None:
        """Try to parse a standard XID. Returns parsed dict or None."""
        m = XID_PATTERN.search(message)
        if not m:
            return None

        pci_addr = m.group(1)
        xid_code = int(m.group(2))

        recommended_action = self.catalog.get_action(xid_code)

        # XID 154: parse action from the log message itself
        if xid_code == 154:
            recommended_action = self._parse_xid154_action(message, recommended_action)

        return {
            "decoded_xid_str": str(xid_code),
            "xid_code": xid_code,
            "pci": pci_addr,
            "description": self.catalog.get_description(xid_code),
            "recommended_action": recommended_action,
        }

    @staticmethod
    def _parse_xid154_action(
        message: str, default: RecommendedAction
    ) -> RecommendedAction:
        """Parse the recommended action directly from an XID 154 log message.

        Format: ... GPU recovery action changed from 0x0 (None) to 0x1 (GPU Reset Required)
        """
        match = re.search(r"\bto\s+0x[0-9a-fA-F]+\s+\(([^)]+)\)", message)
        if not match:
            return default

        recommendation = match.group(1)
        mapping = {
            "GPU Reset Required": RecommendedAction.GPU_RESET_REBOOT,
            "Drain and Reset": RecommendedAction.GPU_RESET_REBOOT,
            "Node Reboot Required": RecommendedAction.GPU_RESET_REBOOT,
            "None": RecommendedAction.NONE,
        }
        return mapping.get(recommendation, RecommendedAction.CRITICAL)

    def _create_health_event(self, resp: dict, message: str):
        """Build and store an XIDEvent."""
        norm_pci = self._normalize_pci_handler(resp["pci"])
        uuid = self._get_gpu_uuid(norm_pci)

        entities = [{"entity_type": "PCI", "entity_value": norm_pci}]
        if uuid:
            entities.append({"entity_type": "GPU_UUID", "entity_value": uuid})

        recommended_action = resp["recommended_action"]

        event = XIDEvent(
            xid_code=resp["xid_code"],
            decoded_xid_str=resp["decoded_xid_str"],
            pci_address=norm_pci,
            gpu_uuid=uuid,
            is_fatal=self._determine_fatality(recommended_action),
            severity=recommended_action.value,
            recommended_action=recommended_action,
            recommended_action_name=recommended_action.name,
            message=message.strip(),
            description=resp.get("description", ""),
            entities=entities,
        )
        self.xid_events.append(event)


# ---------------------------------------------------------------------------
# XidChecker compatibility layer
# ---------------------------------------------------------------------------
class XidChecker:
    """Compatibility wrapper for healthcheck consumers of the older xid_checker.py."""

    def __init__(
        self,
        dmesg_cmd: str = "dmesg -T",
        time_interval: int = 60,
        catalog_path: str | None = None,
        driver_version: str = "",
    ):
        if os.geteuid() != 0:
            raise PermissionError("Root privileges are required to run XidChecker")

        self.dmesg_cmd = dmesg_cmd
        self.time_interval = time_interval
        self.results: dict[str, dict] = {}
        self.catalog_path = catalog_path
        self.driver_version = driver_version

        self.catalog = XIDCatalog(self.catalog_path, self.driver_version)

    def get_dmesg(self) -> str:
        dmesg_cmd_list = shlex.split(self.dmesg_cmd)
        try:
            result = subprocess.run(
                dmesg_cmd_list,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            log.info("Error running Xid check command %s: %s", self.dmesg_cmd, exc)
        except subprocess.TimeoutExpired as exc:
            log.info("%s command timed out: %s", self.dmesg_cmd, exc)
        return ""

    @staticmethod
    def parse_dmesg_timestamp(line):
        """Extract a `dmesg -T` timestamp like `[Thu May  9 14:00:43 2024]`."""
        match = re.match(
            r"\[([A-Za-z]{3} [A-Za-z]{3}\s+\d{1,2} \d{2}:\d{2}:\d{2} \d{4})\]",
            line,
        )
        if not match:
            return None
        try:
            return datetime.strptime(match.group(1), "%a %b %d %H:%M:%S %Y")
        except ValueError:
            return None

    @staticmethod
    def _event_severity(event: XIDEvent) -> str | None:
        if event.severity == RecommendedAction.NONE.value:
            return None
        return event.severity

    @staticmethod
    def _event_description(event: XIDEvent) -> str:
        if event.description:
            return event.description
        message = event.message.strip()
        marker = f"): {event.xid_code},"
        if marker in message:
            description = message.split(marker, 1)[1].strip()
            if description:
                return description
        return f"XID {event.decoded_xid_str}"

    @staticmethod
    def _severity_rank(severity: str) -> int:
        ranks = {
            RecommendedAction.WARNING.value: 1,
            RecommendedAction.CRITICAL.value: 2,
            RecommendedAction.GPU_RESET_REBOOT.value: 3,
        }
        return ranks.get(severity, 0)

    def check_gpu_xid(self):
        categorized_results = {
            "critical": {},
            "gpu_reset_reboot": {},
            "warning": {},
        }
        self.results = {}

        dmesg_output = self.get_dmesg()
        if dmesg_output == "":
            return {
                "categories": categorized_results,
                "results": self.results,
            }

        if "NVRM: Xid" not in dmesg_output:
            log.info("Xid Check: Passed")
            return {
                "categories": categorized_results,
                "results": self.results,
            }

        processor = XIDProcessor(self.catalog)
        for line in dmesg_output.splitlines():
            processor.process_line(line)

        aggregated: dict[str, dict] = {}
        for event in processor.xid_events:
            severity = self._event_severity(event)
            if severity is None:
                continue

            xid_key = str(event.xid_code)
            description = self._event_description(event)
            entry = aggregated.setdefault(
                xid_key,
                {
                    "results": {},
                    "description": description,
                    "severity": severity,
                },
            )

            if entry["description"].startswith("XID ") and not description.startswith(
                "XID "
            ):
                entry["description"] = description

            if self._severity_rank(severity) > self._severity_rank(entry["severity"]):
                entry["severity"] = severity

            pci_counts = entry["results"]
            pci_counts[event.pci_address] = pci_counts.get(event.pci_address, 0) + 1

        for xid_key, entry in aggregated.items():
            severity = entry["severity"]
            self.results[xid_key] = entry
            bucket = categorized_results.get(severity)
            if bucket is None:
                log.warning(
                    "Unknown severity '%s' for XID %s, defaulting to 'warning'",
                    severity,
                    xid_key,
                )
                bucket = categorized_results["warning"]
            bucket[xid_key] = {
                "results": entry["results"],
                "description": entry["description"],
            }

        return {
            "categories": categorized_results,
            "results": self.results,
        }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def _action_label(action: RecommendedAction) -> str:
    labels = {
        RecommendedAction.NONE: "\033[32mNONE\033[0m",
        RecommendedAction.WARNING: "\033[33mWARNING\033[0m",
        RecommendedAction.CRITICAL: "\033[31mCRITICAL\033[0m",
        RecommendedAction.GPU_RESET_REBOOT: "\033[31mGPU_RESET_REBOOT\033[0m",
    }
    return labels.get(action, action.name)


def print_text_report(processor: XIDProcessor):
    """Print a human-readable summary report."""
    events = processor.xid_events

    print(f"\n{'=' * 72}")
    print(" XID Analysis Report")
    print(f"{'=' * 72}")

    if not events:
        print("\n  No XID errors found.\n")
        return

    # --- XID Errors ---
    print(f"\n  XID Errors Found: {len(events)}")
    print(f"  {'-' * 40}")
    for i, ev in enumerate(events, 1):
        fatal_tag = "FATAL" if ev.is_fatal else "NON-FATAL"
        print(f"\n  [{i}] XID {ev.decoded_xid_str}  ({fatal_tag})")
        print(f"      PCI              : {ev.pci_address}")
        print(f"      GPU UUID         : {ev.gpu_uuid or '(not resolved)'}")
        print(f"      Severity         : {ev.severity}")
        print(f"      RecommendedAction: {_action_label(ev.recommended_action)}")
        print(
            f"      Message          : {ev.message[:120]}{'...' if len(ev.message) > 120 else ''}"
        )

    print(f"\n{'=' * 72}")
    print(f" Total XID errors: {len(events)}")
    print(f"{'=' * 72}\n")


def print_json_report(processor: XIDProcessor):
    """Print a JSON report matching the HealthEvent protobuf structure."""
    events = []
    for ev in processor.xid_events:
        events.append(
            {
                "componentClass": "gpu",
                "isFatal": ev.is_fatal,
                "severity": ev.severity,
                "message": ev.message,
                "recommendedAction": ev.recommended_action_name,
                "errorCode": [ev.decoded_xid_str],
                "entitiesImpacted": [
                    {"entityType": e["entity_type"], "entityValue": e["entity_value"]}
                    for e in ev.entities
                ],
            }
        )

    output = {
        "xidErrors": events,
    }
    print(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def resolve_catalog_path(args_catalog: str | None) -> str | None:
    """Resolve the Xid-Catalog.xlsx path. Downloads from NVIDIA if not found locally."""
    if args_catalog:
        p = Path(args_catalog)
        if p.exists():
            return str(p)
        log.error("Specified catalog not found: %s", args_catalog)
        sys.exit(1)

    # Try known locations relative to this script
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "Xid-Catalog.xlsx",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # Attempt to download from NVIDIA
    download_dest = script_dir / "Xid-Catalog.xlsx"
    if _download_catalog(download_dest):
        return str(download_dest)

    return None


def _download_catalog(dest: Path) -> bool:
    """Download Xid-Catalog.xlsx from NVIDIA's documentation site."""
    import urllib.error
    import urllib.request

    log.info("Xid-Catalog.xlsx not found locally, downloading from NVIDIA...")
    log.info("  URL: %s", XID_CATALOG_URL)

    try:
        with urllib.request.urlopen(XID_CATALOG_URL, timeout=30) as response:
            dest.write_bytes(response.read())
        log.info("  Downloaded to: %s", dest)
        return True
    except (TimeoutError, urllib.error.URLError, OSError) as e:
        log.error("  Download failed: %s", e)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Parse syslog for NVIDIA XID errors using NVSentinel logic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --log /var/log/syslog
  %(prog)s --log /var/log/syslog --catalog ./Xid-Catalog.xlsx
  %(prog)s --log /var/log/syslog --driver-version 570.148.08
  journalctl -k | %(prog)s --log -

Generate catalog data if xid_catalog_data.json is missing:
  python3 xid_checker.py --generate-catalog-data xid_catalog_data.json
        """,
    )
    parser.add_argument(
        "--log",
        help="Path to syslog file, or '-' to read from stdin",
    )
    parser.add_argument(
        "--catalog",
        help=(
            "Optional path to Xid-Catalog.xlsx or generated JSON catalog. "
            f"Omit to use {DEFAULT_CATALOG_JSON}."
        ),
    )
    parser.add_argument(
        "--generate-catalog-data",
        metavar="OUTPUT",
        help="Convert Xid-Catalog.xlsx to a JSON catalog data file and exit",
    )
    parser.add_argument(
        "--driver-version",
        help="NVIDIA driver version for NVL5 decoding rules (e.g. 570.148.08)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--xid",
        type=int,
        nargs="+",
        help="Look up one or more XID codes and print their resolution",
    )
    args = parser.parse_args()

    # --- Resolve catalog path ---
    json_mode = args.json

    # Configure logging: default ERROR, verbose bumps to INFO, JSON mode stays ERROR
    log_level = logging.INFO if args.verbose else logging.ERROR
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stderr,
    )

    if args.generate_catalog_data:
        catalog_path = resolve_catalog_path(args.catalog)
        if not catalog_path:
            log.error(
                "Xid-Catalog.xlsx not found. Specify --catalog to generate catalog data."
            )
            sys.exit(1)
        if Path(catalog_path).suffix.lower() == ".json":
            log.error(
                "Generated JSON catalog data must be created from Xid-Catalog.xlsx."
            )
            sys.exit(1)
        output_path = generate_xid_catalog_data(
            catalog_path, args.generate_catalog_data
        )
        log.info("Generated XID catalog data: %s", output_path)
        return

    catalog_path = resolve_catalog_path(args.catalog) if args.catalog else None
    if catalog_path:
        catalog_type = (
            "JSON" if Path(catalog_path).suffix.lower() == ".json" else "XLSX"
        )
        log.info("Using XID catalog %s: %s", catalog_type, catalog_path)
    else:
        log.info("Using XID catalog JSON: %s", DEFAULT_CATALOG_JSON)

    # --- Driver version ---
    driver_version = args.driver_version
    if driver_version:
        log.info("Using driver version: %s", driver_version)
    else:
        log.info("No driver version specified; NVL5 rules will use >= R575 column")

    # --- Load catalog ---
    try:
        catalog = XIDCatalog(catalog_path, driver_version)
    except (FileNotFoundError, ValueError) as exc:
        log.error("%s", exc)
        sys.exit(1)

    # --- XID lookup mode ---
    if args.xid:
        results = [catalog.lookup(code) for code in args.xid]
        if json_mode:
            # Convert RecommendedAction enum to value for JSON serialization
            for r in results:
                r["recommended_action"] = r["recommended_action"].value
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                action = r["recommended_action"]
                print(f"  XID {r['xid_code']:>3}: {action.value}")
                if r.get("requires_nvl5_decode"):
                    print("          Requires NVL5 subcode decode")
                if "nvl5_rules" in r:
                    for rule in r["nvl5_rules"]:
                        print(
                            f"          NVL5 subcode: {rule['mnemonic']} → {rule['resolution']}"
                        )
        return

    # --- Create processor ---
    if not args.log:
        parser.error("--log is required when not using --xid")
    processor = XIDProcessor(catalog)

    # --- Read and process syslog ---
    if args.log == "-":
        for line in sys.stdin:
            processor.process_line(line)
    else:
        try:
            with open(args.log) as f:
                for line in f:
                    processor.process_line(line)
        except FileNotFoundError:
            log.error("log file not found: %s", args.log)
            sys.exit(1)

    log.info("Processed syslog input")

    # --- Output ---
    if args.json:
        print_json_report(processor)
    else:
        print_text_report(processor)


if __name__ == "__main__":
    main()
