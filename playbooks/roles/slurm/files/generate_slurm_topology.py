#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate Slurm topology.yaml files from mgmt node inventory data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Iterable


DEFAULT_COMMAND = (
    "mgmt nodes list "
    "--columns hostname,shape,rack_id,rail_id,network_block_id,cluster_name "
    "--fields role=compute "
    "--format json"
)
DEFAULT_FIELD_ORDER = "hostname,rack_id,rail_id,network_block_id,cluster_name"
SWITCH_NAME_LIMIT = 64
LEAF_NODES_KEY = "__leaf_nodes__"
ACTIVE_FIELDS_KEY = "__active_fields__"
SUBTREE_KEY = "__subtree__"
EMPTY_LEVEL_VALUE = "none"
DEFAULT_SHAPE_FIELD = "shape"
DEFAULT_CROSS_CLUSTER_SWITCH_NAME = "cluster-root"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description=(
            "Run 'mgmt nodes list' and generate Slurm topology.yaml files "
            "for both topology/tree and topology/block."
        )
    )
    parser.add_argument(
        "--command",
        default=DEFAULT_COMMAND,
        help="Command used to collect node data. Ignored when --input-json is set.",
    )
    parser.add_argument(
        "--input-json",
        help="Read node inventory JSON from a file path instead of running the command. Use '-' for stdin.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where the topology files will be written.",
    )
    parser.add_argument(
        "--output-file",
        default="topology.yaml",
        help="Filename for the generated topology YAML containing both tree and block entries.",
    )
    parser.add_argument(
        "--topology-prefix",
        default="mgmt-generated",
        help="Prefix for the topology names written inside the YAML files.",
    )
    parser.add_argument(
        "--field-order",
        default=DEFAULT_FIELD_ORDER,
        help=(
            "Comma-separated field order from lowest to highest level. "
            "The first field is treated as the node name, and each following "
            "field adds a higher topology level."
        ),
    )
    parser.add_argument(
        "--shape-field",
        default=DEFAULT_SHAPE_FIELD,
        help=(
            "Field containing the node shape. When present, the hierarchy can "
            "be reduced per node based on shape-specific rules."
        ),
    )
    parser.add_argument(
        "--block-base-size",
        default="auto",
        help=(
            "Base block size for topology/block. Use an integer or 'auto' "
            "to use the smallest lowest-level group population."
        ),
    )
    parser.add_argument(
        "--cross-cluster",
        action="store_true",
        default=False,
        help=(
            "Add an extra top-level switch that connects all cluster switches "
            "in the tree topology."
        ),
    )
    return parser.parse_args()


def parse_field_order_spec(value: str) -> list[str]:
    fields = [field.strip() for field in value.split(",") if field.strip()]
    if len(fields) < 2:
        raise ValueError(
            "Field order must include at least a node field and one parent field."
        )
    if len(fields) != len(set(fields)):
        raise ValueError("Field order contains duplicate field names.")
    return fields


def parse_field_order_from_command(command: str) -> list[str] | None:
    tokens = shlex.split(command)
    for index, token in enumerate(tokens):
        if token == "--columns" and index + 1 < len(tokens):
            return parse_field_order_spec(tokens[index + 1])
        if token.startswith("--columns="):
            return parse_field_order_spec(token.split("=", 1)[1])
    return None


def remove_shape_field(field_order: list[str], shape_field: str) -> list[str]:
    if shape_field not in field_order:
        return field_order

    filtered = [field for field in field_order if field != shape_field]
    if len(filtered) < 2:
        raise ValueError(
            "Field order must include at least a node field and one parent field "
            "after removing the shape field."
        )
    return filtered


def determine_field_order(
    args: argparse.Namespace,
    raw_records: list[dict[str, object]],
) -> list[str]:
    if args.field_order:
        return remove_shape_field(
            parse_field_order_spec(args.field_order),
            args.shape_field,
        )

    if not args.input_json:
        command_fields = parse_field_order_from_command(args.command)
        if command_fields:
            return remove_shape_field(command_fields, args.shape_field)

    if not raw_records:
        # Return default field order for empty topology
        default_fields = "hostname,rack_id,rail_id,network_block_id,cluster_name"
        return remove_shape_field(
            parse_field_order_spec(default_fields),
            args.shape_field,
        )

    first_record = raw_records[0]
    if not isinstance(first_record, dict):
        raise ValueError("Inventory JSON must be a list of objects.")

    return remove_shape_field(
        parse_field_order_spec(",".join(first_record.keys())),
        args.shape_field,
    )


def normalize_field_value(value: object) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    if not normalized:
        return None

    if normalized.lower() in {"none", "null"}:
        return None

    return normalized


def sortable_value(value: str | None) -> list[object]:
    return natural_sort_key(value if value is not None else EMPTY_LEVEL_VALUE)


def load_records(args: argparse.Namespace) -> tuple[list[dict[str, str | None]], list[str]]:
    if args.input_json:
        if args.input_json == "-":
            raw_output = sys.stdin.read()
        else:
            raw_output = Path(args.input_json).read_text(encoding="utf-8")
    else:
        result = subprocess.run(
            shlex.split(args.command),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                "Inventory command failed with exit code "
                f"{result.returncode}: {result.stderr.strip() or result.stdout.strip()}"
            )
        raw_output = result.stdout

    try:
        records = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ValueError("Inventory data is not valid JSON.") from exc

    if not isinstance(records, list):
        raise ValueError("Inventory JSON must be a list of node objects.")

    field_order = determine_field_order(args, records)
    node_field = field_order[0]
    top_field = field_order[-1]
    shape_field = args.shape_field

    normalized_records: list[dict[str, str | None]] = []
    seen_node_names: set[str] = set()

    for index, raw_record in enumerate(records, start=1):
        if not isinstance(raw_record, dict):
            raise ValueError(f"Record {index} is not a JSON object.")

        if node_field not in raw_record:
            raise ValueError(
                f"Record {index} is missing required node field: {node_field}"
            )

        if top_field not in raw_record:
            raise ValueError(
                f"Record {index} is missing required top-level field: {top_field}"
            )

        node_name = normalize_field_value(raw_record.get(node_field))
        if node_name is None:
            raise ValueError(f"Record {index} has an empty node field: {node_field}")

        top_value = normalize_field_value(raw_record.get(top_field))
        if top_value is None:
            raise ValueError(f"Record {index} has an empty top-level field: {top_field}")

        if node_name in seen_node_names:
            raise ValueError(f"Duplicate node value found in inventory: {node_name}")
        seen_node_names.add(node_name)

        normalized_record: dict[str, str | None] = {}
        for field in field_order:
            if field == node_field:
                normalized_record[field] = node_name
            elif field == top_field:
                normalized_record[field] = top_value
            else:
                normalized_record[field] = normalize_field_value(raw_record.get(field))

        normalized_record[shape_field] = normalize_field_value(raw_record.get(shape_field))
        normalized_records.append(normalized_record)

    return normalized_records, field_order


def natural_sort_key(value: str) -> list[object]:
    parts = re.split(r"(\d+)", value)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def sanitize_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_:-]+", "-", value.strip())
    token = re.sub(r"-{2,}", "-", token).strip("-_")
    return token or "unnamed"


def shorten_with_hash(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value

    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    keep = max(1, limit - len(digest) - 1)
    shortened = value[:keep].rstrip("-_")
    return f"{shortened}-{digest}"


def make_switch_name(level: str, *parts: str) -> str:
    filtered_parts = [part for part in parts if part]
    if filtered_parts:
        base = f"{level}::{':'.join(filtered_parts)}"
    else:
        base = level
    return shorten_with_hash(sanitize_token(base), SWITCH_NAME_LIMIT)


def yaml_quote(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def hostlist(values: Iterable[str]) -> str:
    return ",".join(sorted(values, key=natural_sort_key))


def split_field_name(field_name: str) -> list[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", field_name)
    return [part for part in re.split(r"[_\W]+", normalized) if part]


def build_field_aliases(field_order: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    used_aliases: set[str] = set()

    for field_name in field_order[1:]:
        parts = [part.lower() for part in split_field_name(field_name)]
        base_parts = parts[:]

        if len(base_parts) > 1 and base_parts[-1] in {"id", "name"}:
            base_parts = base_parts[:-1]

        if not base_parts:
            base_parts = parts or ["field"]

        alias = sanitize_token("-".join(base_parts)) or "field"
        candidate = alias
        suffix_index = 2
        while candidate in used_aliases:
            candidate = f"{alias}-{suffix_index}"
            suffix_index += 1

        aliases[field_name] = candidate
        used_aliases.add(candidate)

    return aliases


def field_alias(field_name: str, aliases: dict[str, str]) -> str:
    if field_name in aliases:
        return aliases[field_name]

    parts = split_field_name(field_name)
    if not parts:
        return "fld"
    alias = "".join(part[0].lower() for part in parts[:4])
    return alias or sanitize_token(field_name)[:3] or "fld"


def value_token(value: str, field_name: str, top_level: bool = False) -> str:
    sanitized = sanitize_token(value)
    if value.startswith("ocid1.") or field_name.lower() == "rack_id":
        return sanitized[-8:]
    limit = 24 if top_level else 16
    return shorten_with_hash(sanitized, limit)


def path_value_tokens(
    path_values: list[str],
    path_field_names: list[str],
) -> list[str]:
    return [
        value_token(
            value,
            path_field_names[index],
            top_level=(index == 0),
        )
        for index, value in enumerate(path_values)
    ]


def selected_lower_fields_for_shape(
    shape_value: str | None,
    lower_fields_low_to_high: list[str],
) -> list[str]:
    if not shape_value:
        preferred = ["rack_id"]
        preferred_set = set(preferred)
        return [field for field in lower_fields_low_to_high if field in preferred_set]

    shape_upper = shape_value.upper()

    if "GPU.GB" in shape_upper:
        preferred = ["rack_id", "rail_id", "network_block_id"]
    elif (
        shape_upper in {"BM.GPU4.8", "BM.GPU.B4.8", "BM.GPU.A100-V2.8"}
        or "HPC" in shape_upper
        or "OPTIMIZED" in shape_upper
    ):
        preferred = ["rack_id", "network_block_id"]
    elif "GPU" in shape_upper:
        preferred = ["rail_id", "network_block_id"]
    else:
        preferred = ["rack_id"]

    preferred_set = set(preferred)
    return [field for field in lower_fields_low_to_high if field in preferred_set]


def build_hierarchy(
    records: list[dict[str, str | None]],
    field_order: list[str],
    shape_field: str,
) -> OrderedDict[str, object]:
    hierarchy: OrderedDict[str, object] = OrderedDict()
    node_field = field_order[0]
    top_field = field_order[-1]
    lower_parent_fields_low_to_high = field_order[1:-1]
    lower_parent_fields_high_to_low = list(reversed(lower_parent_fields_low_to_high))

    # Handle empty records - create default topology
    if not records:
        subtree: OrderedDict[str, object] = OrderedDict()
        subtree[LEAF_NODES_KEY] = ["non_existent_node"]
        hierarchy["initial_startup_bugfix"] = {
            ACTIVE_FIELDS_KEY: [],
            SUBTREE_KEY: subtree,
        }
        return hierarchy

    def sort_tuple(item: dict[str, str | None]) -> tuple[tuple[object, ...], ...]:
        return tuple(
            tuple(sortable_value(item[field]))
            for field in [top_field, *lower_parent_fields_high_to_low, node_field]
        )

    sorted_records = sorted(records, key=sort_tuple)

    grouped_records: OrderedDict[str, list[dict[str, str | None]]] = OrderedDict()
    for record in sorted_records:
        top_value = record[top_field]
        assert top_value is not None
        grouped_records.setdefault(top_value, []).append(record)

    for top_value, group_records in grouped_records.items():
        active_fields = [
            field
            for field in lower_parent_fields_high_to_low
            if any(
                field in selected_lower_fields_for_shape(
                    record.get(shape_field),
                    lower_parent_fields_low_to_high,
                )
                and record[field] is not None
                for record in group_records
            )
        ]

        subtree: OrderedDict[str, object] = OrderedDict()
        for record in group_records:
            selected_fields = set(
                selected_lower_fields_for_shape(
                    record.get(shape_field),
                    lower_parent_fields_low_to_high,
                )
            )
            cursor = subtree
            for field in active_fields:
                field_value = (
                    record[field]
                    if field in selected_fields and record[field] is not None
                    else EMPTY_LEVEL_VALUE
                )
                cursor = cursor.setdefault(field_value, OrderedDict())
            leaf_nodes = cursor.setdefault(LEAF_NODES_KEY, [])
            leaf_nodes.append(record[node_field])

        hierarchy[top_value] = {
            ACTIVE_FIELDS_KEY: active_fields,
            SUBTREE_KEY: subtree,
        }

    return hierarchy


def collect_leaf_groups(
    hierarchy: OrderedDict[str, object],
    path_values: list[str] | None = None,
) -> list[tuple[list[str], list[str]]]:
    if path_values is None:
        path_values = []

    groups: list[tuple[list[str], list[str]]] = []
    for key, value in hierarchy.items():
        if key == LEAF_NODES_KEY:
            groups.append((path_values[:], list(value)))
            continue
        groups.extend(collect_leaf_groups(value, [*path_values, key]))
    return groups


def collect_top_level_group_sizes(hierarchy: OrderedDict[str, object]) -> list[int]:
    sizes: list[int] = []
    for group_data in hierarchy.values():
        subtree = group_data[SUBTREE_KEY]
        leaf_groups = collect_leaf_groups(subtree)
        sizes.append(sum(len(nodes) for _, nodes in leaf_groups))
    return sizes


def compute_block_sizes(
    hierarchy: OrderedDict[str, object],
    base_size_arg: str,
) -> list[int]:
    group_sizes = [
        len(nodes)
        for group_data in hierarchy.values()
        for _, nodes in collect_leaf_groups(group_data[SUBTREE_KEY])
    ]

    if not group_sizes:
        if base_size_arg == "auto":
            return [1]  # Default block size for empty topology
        try:
            base_size = int(base_size_arg)
        except ValueError as exc:
            raise ValueError("--block-base-size must be an integer or 'auto'.") from exc
        if base_size < 1:
            raise ValueError("--block-base-size must be greater than zero.")
        return [base_size]

    if base_size_arg == "auto":
        base_size = min(group_sizes)
    else:
        try:
            base_size = int(base_size_arg)
        except ValueError as exc:
            raise ValueError("--block-base-size must be an integer or 'auto'.") from exc
        if base_size < 1:
            raise ValueError("--block-base-size must be greater than zero.")
        if any(size < base_size for size in group_sizes):
            raise ValueError(
                "The requested block base size is larger than at least one lowest-level group."
            )

    top_level_sizes = collect_top_level_group_sizes(hierarchy)
    max_cluster_size = max(top_level_sizes)
    block_sizes = [base_size]
    next_size = base_size * 2
    while next_size <= max_cluster_size:
        block_sizes.append(next_size)
        next_size *= 2

    return block_sizes


def render_tree_yaml(
    hierarchy: OrderedDict[str, object],
    field_order: list[str],
    topology_name: str,
    cross_cluster: bool,
) -> str:
    switches: list[dict[str, str]] = []
    top_field = field_order[-1]
    field_aliases = build_field_aliases(field_order)
    cluster_switch_names: list[str] = []

    def switch_name_for_path(
        field_name: str,
        path_values: list[str],
        path_field_names: list[str],
    ) -> str:
        if (
            len(path_values) == 1
            and not path_values[0].startswith("ocid1.")
            and field_name.lower() != "rack_id"
        ):
            return shorten_with_hash(sanitize_token(path_values[0]), SWITCH_NAME_LIMIT)
        return make_switch_name(
            field_alias(field_name, field_aliases),
            *path_value_tokens(path_values, path_field_names),
        )

    def walk_tree(
        subtree: OrderedDict[str, object],
        active_fields: list[str],
        level_index: int,
        path_values: list[str],
        path_field_names: list[str],
    ) -> tuple[list[str], list[dict[str, str]]]:
        current_field = active_fields[level_index]
        child_switch_names: list[str] = []
        rendered_switches: list[dict[str, str]] = []

        for value, child in subtree.items():
            if value == LEAF_NODES_KEY:
                continue

            current_path = [*path_values, value]
            current_path_fields = [*path_field_names, current_field]
            switch_name = switch_name_for_path(
                current_field,
                current_path,
                current_path_fields,
            )

            if level_index == len(active_fields) - 1:
                leaf_nodes = child.get(LEAF_NODES_KEY, [])
                rendered_switches.append(
                    {
                        "switch": switch_name,
                        "nodes": hostlist(leaf_nodes),
                    }
                )
            else:
                descendant_switch_names, descendant_rendered_switches = walk_tree(
                    child,
                    active_fields,
                    level_index + 1,
                    current_path,
                    current_path_fields,
                )
                rendered_switches.append(
                    {
                        "switch": switch_name,
                        "children": ",".join(descendant_switch_names),
                    }
                )
                rendered_switches.extend(descendant_rendered_switches)

            child_switch_names.append(switch_name)

        return child_switch_names, rendered_switches

    for top_value, group_data in hierarchy.items():
        active_fields = group_data[ACTIVE_FIELDS_KEY]
        subtree = group_data[SUBTREE_KEY]
        top_switch = switch_name_for_path(top_field, [top_value], [top_field])
        cluster_switch_names.append(top_switch)

        if not active_fields:
            leaf_nodes = subtree.get(LEAF_NODES_KEY, [])
            switches.append(
                {
                    "switch": top_switch,
                    "nodes": hostlist(leaf_nodes),
                }
            )
            continue

        child_switch_names, child_rendered_switches = walk_tree(
            subtree,
            active_fields,
            0,
            [top_value],
            [top_field],
        )
        switches.append(
            {
                "switch": top_switch,
                "children": ",".join(child_switch_names),
            }
        )
        switches.extend(child_rendered_switches)

    if cross_cluster and cluster_switch_names:
        switches.insert(
            0,
            {
                "switch": DEFAULT_CROSS_CLUSTER_SWITCH_NAME,
                "children": ",".join(cluster_switch_names),
            },
        )

    lines = [
        f"- topology: {yaml_quote(topology_name)}",
        "  cluster_default: true",
        "  tree:",
        "    switches:",
    ]

    for switch in switches:
        lines.append(f"      - switch: {yaml_quote(switch['switch'])}")
        if "children" in switch:
            lines.append(f"        children: {yaml_quote(switch['children'])}")
        if "nodes" in switch:
            lines.append(f"        nodes: {yaml_quote(switch['nodes'])}")

    lines.append("")
    return "\n".join(lines)


def render_block_yaml(
    hierarchy: OrderedDict[str, object],
    field_order: list[str],
    topology_name: str,
    block_sizes: list[int],
) -> str:
    blocks: list[dict[str, str]] = []
    top_field = field_order[-1]
    field_aliases = build_field_aliases(field_order)

    for top_value, group_data in hierarchy.items():
        active_fields = group_data[ACTIVE_FIELDS_KEY]
        subtree = group_data[SUBTREE_KEY]
        lowest_parent_field = active_fields[-1] if active_fields else top_field

        for lower_path_values, nodes in collect_leaf_groups(subtree):
            path_values = [top_value, *lower_path_values]
            path_field_names = [top_field, *active_fields[: len(lower_path_values)]]
            block_name = make_switch_name(
                "blk",
                field_alias(lowest_parent_field, field_aliases),
                *path_value_tokens(path_values, path_field_names),
            )
            blocks.append(
                {
                    "block": block_name,
                    "nodes": hostlist(nodes),
                }
            )

    lines = [
        f"- topology: {yaml_quote(topology_name)}",
        "  cluster_default: false",
        "  block:",
        "    block_sizes:",
    ]

    for block_size in block_sizes:
        lines.append(f"      - {block_size}")

    lines.append("    blocks:")
    for block in blocks:
        lines.append(f"      - block: {yaml_quote(block['block'])}")
        lines.append(f"        nodes: {yaml_quote(block['nodes'])}")

    lines.append("")
    return "\n".join(lines)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_path = output_dir / args.output_file

    records, field_order = load_records(args)
    hierarchy = build_hierarchy(records, field_order, args.shape_field)
    block_sizes = compute_block_sizes(hierarchy, args.block_base_size)

    command_text = args.command if not args.input_json else f"input-json:{args.input_json}"
    tree_content = render_tree_yaml(
        hierarchy=hierarchy,
        field_order=field_order,
        topology_name="tree",
        cross_cluster=args.cross_cluster,
    )
    block_content = render_block_yaml(
        hierarchy=hierarchy,
        field_order=field_order,
        topology_name="block",
        block_sizes=block_sizes,
    )

    combined_content = "\n".join(
        [
            "---",
            "# Generated by scripts/generate_slurm_topology.py",
            f"# Source command: {command_text}",
            f"# Field order (low->high): {', '.join(field_order)}",
            f"# Block base size: {block_sizes[0] if block_sizes else 'n/a'}",
            tree_content.rstrip(),
            block_content.rstrip(),
            "",
        ]
    )

    write_file(output_path, combined_content)

    print(f"Wrote {output_path}")
    print(f"Generated {len(records)} nodes across {len(hierarchy)} top-level group(s).")
    print(f"Field order: {', '.join(field_order)}")
    print(f"Block sizes: {', '.join(str(size) for size in block_sizes)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
