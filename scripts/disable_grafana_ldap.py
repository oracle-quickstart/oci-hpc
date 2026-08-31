#!/usr/bin/env python3
"""Disable Grafana LDAP login on an existing deployment.

This script is intended to run on the node that already hosts Grafana.
It disables Grafana LDAP authentication and returns Grafana to local-user
authentication without changing the controller LDAP service itself.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Disable Grafana LDAP login for an existing OCI HPC deployment.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--grafana-ini",
        default="/etc/grafana/grafana.ini",
        help="Path to grafana.ini",
    )
    parser.add_argument(
        "--ldap-config",
        default="/etc/grafana/ldap.toml",
        help="Path to Grafana LDAP config file",
    )
    parser.add_argument(
        "--ldap-host",
        default="controller.cluster",
        help="LDAP hostname previously configured for Grafana",
    )
    parser.add_argument(
        "--hosts-path",
        default="/etc/hosts",
        help="Path to hosts file",
    )
    parser.add_argument(
        "--service-name",
        default="grafana-server",
        help="Systemd service name for Grafana",
    )
    parser.add_argument(
        "--restart",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Restart Grafana after applying changes",
    )
    parser.add_argument(
        "--remove-host-alias",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Remove the LDAP host alias from the hosts file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files or restarting services",
    )
    return parser.parse_args()


def require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("This script must be run as root.")


def backup_file(path: pathlib.Path, dry_run: bool) -> None:
    if not path.exists():
        return
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup = path.with_name(f"{path.name}.{timestamp}.bak")
    print(f"Backing up {path} -> {backup}")
    if not dry_run:
        shutil.copy2(path, backup)


def ensure_ini_option(lines: list[str], section: str, option: str, value: str) -> list[str]:
    section_header = f"[{section}]"
    option_pattern = re.compile(rf"^\s*[;#]?\s*{re.escape(option)}\s*=")
    start = None
    end = len(lines)

    for index, line in enumerate(lines):
        if line.strip() == section_header:
            start = index
            break

    if start is None:
        if lines and lines[-1].strip():
            lines.append("\n")
        lines.extend([f"{section_header}\n", f"{option} = {value}\n"])
        return lines

    for index in range(start + 1, len(lines)):
        if lines[index].startswith("[") and lines[index].rstrip().endswith("]"):
            end = index
            break

    for index in range(start + 1, end):
        if option_pattern.match(lines[index]):
            lines[index] = f"{option} = {value}\n"
            return lines

    lines.insert(end, f"{option} = {value}\n")
    return lines


def update_grafana_ini(path: pathlib.Path, dry_run: bool) -> None:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    settings = [
        ("auth.ldap", "enabled", "false"),
        ("auth.ldap", "allow_sign_up", "false"),
    ]
    for section, option, value in settings:
        lines = ensure_ini_option(lines, section, option, value)

    new_content = "".join(lines)
    if new_content == content:
        print(f"No changes needed in {path}")
        return

    print(f"Updating {path}")
    if dry_run:
        return
    path.write_text(new_content, encoding="utf-8")


def remove_file(path: pathlib.Path, dry_run: bool) -> None:
    if not path.exists():
        print(f"{path} is already absent")
        return
    print(f"Removing {path}")
    if not dry_run:
        path.unlink()


def remove_host_alias(hosts_path: pathlib.Path, ldap_host: str, dry_run: bool) -> None:
    if not hosts_path.exists():
        raise SystemExit(f"Hosts file not found: {hosts_path}")

    content = hosts_path.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered = [
        entry for entry in content
        if not re.search(rf"(^|\s){re.escape(ldap_host)}(\s|$)", entry)
    ]

    if filtered == content:
        print(f"No {ldap_host} entry found in {hosts_path}")
        return

    print(f"Removing {ldap_host} entry from {hosts_path}")
    if not dry_run:
        hosts_path.write_text("".join(filtered), encoding="utf-8")


def restart_service(service_name: str, dry_run: bool) -> None:
    print(f"Restarting {service_name}")
    if dry_run:
        return
    subprocess.run(["systemctl", "restart", service_name], check=True)


def validate_paths(args: argparse.Namespace) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    grafana_ini = pathlib.Path(args.grafana_ini)
    ldap_config = pathlib.Path(args.ldap_config)
    hosts_path = pathlib.Path(args.hosts_path)

    if not grafana_ini.exists():
        raise SystemExit(f"Grafana ini not found: {grafana_ini}")
    if not hosts_path.exists():
        raise SystemExit(f"Hosts file not found: {hosts_path}")

    return grafana_ini, ldap_config, hosts_path


def main() -> int:
    args = parse_args()
    require_root()

    grafana_ini, ldap_config, hosts_path = validate_paths(args)

    backup_file(grafana_ini, args.dry_run)
    if ldap_config.exists():
        backup_file(ldap_config, args.dry_run)
    if args.remove_host_alias:
        backup_file(hosts_path, args.dry_run)

    update_grafana_ini(grafana_ini, args.dry_run)
    remove_file(ldap_config, args.dry_run)

    if args.remove_host_alias:
        remove_host_alias(hosts_path, args.ldap_host, args.dry_run)

    if args.restart:
        restart_service(args.service_name, args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
