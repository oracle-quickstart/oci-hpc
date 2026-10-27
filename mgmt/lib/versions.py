"""Resolve published versions and persist the shared Dr HPC installation pin."""

import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import urlopen

import yaml

MANIFEST_PATH = Path("/config/playbooks/versions.yaml")


def get_latest_dr_hpc_version(package_url: str, json_path: str) -> str:
    """Read a version from JSON relative to a package URL (or URL template)."""
    try:
        with urlopen(urljoin(package_url, json_path), timeout=15) as response:
            metadata = json.load(response)
    except (OSError, URLError, ValueError) as error:
        # HTTP exceptions can contain the pre-authenticated download URL.
        raise ValueError(f"Unable to read latest-version metadata ({type(error).__name__})") from None
    version = metadata.get("version") if isinstance(metadata, dict) else None
    if not isinstance(version, str) or not version or not all(
        char.isascii() and (char.isalnum() or char in ".+_-") for char in version
    ):
        raise ValueError("Latest-version metadata must contain a valid version string")
    return version


@contextmanager
def dr_hpc_version(version=None):
    """Update both OS pins, holding the rollout lock until the caller finishes."""
    with MANIFEST_PATH.with_suffix(".yaml.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another Dr HPC reconfiguration is already running") from None

        original = MANIFEST_PATH.read_text(encoding="utf-8")
        try:
            manifest = yaml.safe_load(original)
            sources = manifest["dr_hpc"]
            for selector in ("ubuntu", "oraclelinux"):
                if not isinstance(sources[selector]["url"], str) or not isinstance(
                    sources[selector]["version"], str
                ):
                    raise TypeError("Dr HPC sources require string URLs and versions")
            root = yaml.compose(original, Loader=yaml.SafeLoader)
            role = next(value for key, value in root.value if key.value == "dr_hpc")
            version_nodes = [
                value
                for _, source in role.value
                for key, value in source.value
                if key.value == "version"
            ]
        except (yaml.YAMLError, KeyError, TypeError, AttributeError, StopIteration):
            raise ValueError("Invalid Dr HPC source definitions in versions.yaml") from None

        if version is None:
            version = get_latest_dr_hpc_version(sources["ubuntu"]["url"], "../latest.json")
        if not isinstance(version, str) or not version or not all(
            char.isascii() and (char.isalnum() or char in ".+_-") for char in version
        ):
            raise ValueError("Dr HPC version must be a nonempty package-version string")

        updated = original
        for node in sorted(version_nodes, key=lambda node: node.start_mark.index, reverse=True):
            if node.value != version:
                updated = f"{updated[:node.start_mark.index]}{json.dumps(version)}{updated[node.end_mark.index:]}"

        if updated != original:
            attributes = MANIFEST_PATH.stat()
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=MANIFEST_PATH.parent,
                    prefix=f".{MANIFEST_PATH.name}.", delete=False,
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    temporary.write(updated)
                    temporary.flush()
                    temporary_attributes = os.fstat(temporary.fileno())
                    if (temporary_attributes.st_uid, temporary_attributes.st_gid) != (
                        attributes.st_uid, attributes.st_gid
                    ):
                        os.fchown(temporary.fileno(), attributes.st_uid, attributes.st_gid)
                    os.fchmod(temporary.fileno(), stat.S_IMODE(attributes.st_mode))
                    os.fsync(temporary.fileno())
                if MANIFEST_PATH.read_text(encoding="utf-8") != original:
                    raise ValueError("versions.yaml changed during version resolution; retry the command")
                os.replace(temporary_path, MANIFEST_PATH)
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

        yield version
