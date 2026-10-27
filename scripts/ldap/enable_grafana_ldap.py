#!/usr/bin/env python3
"""Enable Grafana LDAP login on an existing deployment.

This script is intended to run on the node that already hosts Grafana.
It enables Grafana LDAP authentication against the existing OpenLDAP
deployment used by the Slurm controller.
"""

from __future__ import annotations

import argparse
import grp
import ipaddress
import os
import pathlib
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import textwrap
from datetime import datetime


COMMON_CA_PATHS = [
    "/etc/ssl/certs/cluster-ca.crt",
    "/config/key/cluster-ca.crt",
    "/usr/local/share/ca-certificates/cluster-ca.crt",
    "/etc/pki/ca-trust/source/anchors/cluster-ca.crt",
]


def is_ipv4_address(value: str) -> bool:
    try:
        socket.inet_aton(value)
        return True
    except OSError:
        return False


def is_private_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        return address.is_private and not address.is_loopback and not address.is_link_local
    except ValueError:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable Grafana LDAP login for an existing OCI HPC deployment.",
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
        "--grafana-group",
        default="grafana",
        help="OS group that Grafana runs under",
    )
    parser.add_argument(
        "--service-name",
        default="grafana-server",
        help="Systemd service name for Grafana",
    )
    parser.add_argument(
        "--ldap-host",
        default="controller.cluster",
        help="LDAP hostname Grafana should use. This must match the LDAP certificate SAN.",
    )
    parser.add_argument(
        "--controller-ip",
        default="",
        help="Optional controller IP reachable from the Grafana host, usually the controller private IP. If provided, the script ensures /etc/hosts resolves --ldap-host.",
    )
    parser.add_argument(
        "--hosts-path",
        default="/etc/hosts",
        help="Path to hosts file",
    )
    parser.add_argument(
        "--root-ca-cert",
        default="/etc/ssl/certs/cluster-ca.crt",
        help="Path to the cluster CA certificate on the Grafana host",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=636,
        help="LDAP TLS port",
    )
    parser.add_argument(
        "--search-base",
        action="append",
        default=None,
        help="LDAP search base. Repeat to add multiple bases. Defaults to ou=People,dc=local.",
    )
    parser.add_argument(
        "--bind-dn-template",
        default="cn=%s,ou=People,dc=local",
        help="LDAP bind DN template used for single-bind auth",
    )
    parser.add_argument(
        "--search-filter",
        default="(uid=%s)",
        help="LDAP search filter",
    )
    parser.add_argument(
        "--name-attr",
        default="displayName",
        help="LDAP attribute mapped to Grafana name",
    )
    parser.add_argument(
        "--surname-attr",
        default="sn",
        help="LDAP attribute mapped to Grafana surname",
    )
    parser.add_argument(
        "--username-attr",
        default="uid",
        help="LDAP attribute mapped to Grafana username",
    )
    parser.add_argument(
        "--member-of-attr",
        default="memberOf",
        help="LDAP attribute used for group membership",
    )
    parser.add_argument(
        "--email-attr",
        default="",
        help="Optional LDAP attribute mapped to Grafana email",
    )
    parser.add_argument(
        "--admin-group-dn",
        default="cn=grafana-admins,ou=Group,dc=local",
        help="LDAP group DN mapped to Grafana Admin",
    )
    parser.add_argument(
        "--editor-group-dn",
        default="cn=grafana-editors,ou=Group,dc=local",
        help="LDAP group DN mapped to Grafana Editor",
    )
    parser.add_argument(
        "--viewer-group-dn",
        default="*",
        help="LDAP group DN mapped to Grafana Viewer",
    )
    parser.add_argument(
        "--restart",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Restart Grafana after applying changes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files or restarting services",
    )
    args = parser.parse_args()
    if args.search_base is None:
        args.search_base = ["ou=People,dc=local"]
    return args


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


def atomic_write(path: pathlib.Path, content: str, owner: str, group: str, mode: int, dry_run: bool) -> None:
    print(f"Writing {path}")
    if dry_run:
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(group).gr_gid

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.chown(tmp_name, uid, gid)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def validate_file_metadata(path: pathlib.Path, owner: str, group: str, mode: int, dry_run: bool) -> None:
    expected_mode = oct(mode)
    if dry_run:
        print(f"Would validate {path} owner={owner} group={group} mode={expected_mode}")
        return

    stat_result = path.stat()
    actual_owner = pwd.getpwuid(stat_result.st_uid).pw_name
    actual_group = grp.getgrgid(stat_result.st_gid).gr_name
    actual_mode = oct(stat_result.st_mode & 0o777)

    if actual_owner != owner or actual_group != group or actual_mode != expected_mode:
        raise SystemExit(
            f"{path} has {actual_owner}:{actual_group} {actual_mode}, "
            f"expected {owner}:{group} {expected_mode}"
        )


def validate_tls(args: argparse.Namespace) -> None:
    openssl = shutil.which("openssl")
    if openssl is None:
        print("Skipping TLS validation because openssl is not installed")
        return

    command = [
        openssl,
        "s_client",
        "-connect",
        f"{args.ldap_host}:{args.port}",
        "-verify_hostname",
        args.ldap_host,
        "-CAfile",
        args.root_ca_cert,
    ]
    print(f"Validating LDAP TLS hostname and CA trust against {args.ldap_host}:{args.port}")
    result = subprocess.run(
        command,
        input=b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "TLS validation failed for the configured LDAP host.\n"
            + result.stdout.decode("utf-8", errors="replace")
        )


def discover_local_ip() -> str:
    result = subprocess.run(
        ["hostname", "-I"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        for token in result.stdout.split():
            if is_ipv4_address(token) and not token.startswith("127."):
                return token
    raise SystemExit(
        "Unable to determine a local non-loopback IPv4 address automatically. "
        "Re-run with --controller-ip."
    )


def lookup_ipv4_addresses(hostname: str) -> list[str]:
    addresses: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None):
            if family == socket.AF_INET and sockaddr[0] not in addresses:
                addresses.append(sockaddr[0])
    except socket.gaierror:
        return []
    return addresses


def derive_controller_host_candidates() -> list[str]:
    candidates: list[str] = []
    local_names = [socket.gethostname(), socket.getfqdn()]
    for name in local_names:
        if not name:
            continue
        candidates.append(name)
        if "-monitoring" in name:
            candidates.append(name.replace("-monitoring", "-controller"))
        if name.endswith("monitoring"):
            candidates.append(f"{name[:-10]}controller")
    candidates.extend(["controller", "controller.cluster"])

    unique: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


def infer_controller_private_ip() -> str:
    for candidate in derive_controller_host_candidates():
        for address in lookup_ipv4_addresses(candidate):
            if is_private_ipv4(address):
                print(f"Inferred controller private IP {address} from hostname {candidate}")
                return address
    return ""


def ensure_hosts_alias(hosts_path: pathlib.Path, ldap_host: str, controller_ip: str, dry_run: bool) -> str:
    inferred_controller_ip = infer_controller_private_ip()
    if not controller_ip:
        if inferred_controller_ip:
            controller_ip = inferred_controller_ip
        else:
            existing_ips = lookup_ipv4_addresses(ldap_host)
            private_existing_ips = [ip for ip in existing_ips if is_private_ipv4(ip)]
            if private_existing_ips:
                print(f"{ldap_host} already resolves to private IP(s): {', '.join(private_existing_ips)}")
                return private_existing_ips[0]
            if existing_ips:
                raise SystemExit(
                    f"{ldap_host} resolves only to non-private IP(s): {', '.join(existing_ips)}. "
                    "Re-run with --controller-ip using the controller private IP."
                )
            controller_ip = discover_local_ip()
            print(f"{ldap_host} does not resolve; using local host IP {controller_ip}")
    elif not is_private_ipv4(controller_ip) and inferred_controller_ip:
        print(
            f"Provided controller IP {controller_ip} is not private; "
            f"using inferred private controller IP {inferred_controller_ip} instead"
        )
        controller_ip = inferred_controller_ip

    current_ips = set()
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(ldap_host, None):
            if family == socket.AF_INET:
                current_ips.add(sockaddr[0])
    except socket.gaierror:
        pass

    if current_ips == {controller_ip}:
        print(f"{ldap_host} already resolves to {controller_ip}")
        return controller_ip

    line = f"{controller_ip} {ldap_host} controller # grafana-ldap\n"
    if current_ips:
        print(f"Updating {ldap_host} from {', '.join(sorted(current_ips))} to {controller_ip} in {hosts_path}")
    else:
        print(f"Adding {ldap_host} -> {controller_ip} to {hosts_path}")
    if dry_run:
        return controller_ip

    existing_lines = hosts_path.read_text(encoding="utf-8").splitlines(keepends=True)
    filtered_lines = [
        entry for entry in existing_lines
        if not re.search(rf"(^|\s){re.escape(ldap_host)}(\s|$)", entry)
    ]
    filtered_lines.append(line)
    hosts_path.write_text("".join(filtered_lines), encoding="utf-8")
    return controller_ip


def ensure_host_resolves(ldap_host: str, expected_ip: str = "") -> None:
    try:
        addresses = {
            sockaddr[0]
            for family, _, _, _, sockaddr in socket.getaddrinfo(ldap_host, None)
            if family == socket.AF_INET
        }
    except socket.gaierror as exc:
        raise SystemExit(f"{ldap_host} does not resolve after hosts update: {exc}") from exc
    if expected_ip and expected_ip not in addresses:
        raise SystemExit(
            f"{ldap_host} resolves to {', '.join(sorted(addresses))}, expected {expected_ip}"
        )


def render_ldap_toml(args: argparse.Namespace) -> str:
    bases = ", ".join(f'"{base}"' for base in args.search_base)
    email_line = ""
    if args.email_attr:
        email_line = f'email = "{args.email_attr}"\n'

    return textwrap.dedent(
        f"""\
        [[servers]]
        host = "{args.ldap_host}"
        port = {args.port}
        use_ssl = true
        start_tls = false
        ssl_skip_verify = false
        timeout = 10
        bind_dn = "{args.bind_dn_template}"
        search_filter = "{args.search_filter}"
        search_base_dns = [{bases}]
        root_ca_cert = "{args.root_ca_cert}"

        [servers.attributes]
        name = "{args.name_attr}"
        surname = "{args.surname_attr}"
        username = "{args.username_attr}"
        member_of = "{args.member_of_attr}"
        {email_line}\

        [[servers.group_mappings]]
        group_dn = "{args.admin_group_dn}"
        org_role = "Admin"
        grafana_admin = true

        [[servers.group_mappings]]
        group_dn = "{args.editor_group_dn}"
        org_role = "Editor"

        [[servers.group_mappings]]
        group_dn = "{args.viewer_group_dn}"
        org_role = "Viewer"
        """
    )


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


def update_grafana_ini(path: pathlib.Path, ldap_config: str, dry_run: bool) -> None:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    settings = [
        ("auth.ldap", "enabled", "true"),
        ("auth.ldap", "config_file", ldap_config),
        ("auth.ldap", "allow_sign_up", "true"),
        ("auth.ldap", "skip_org_role_sync", "false"),
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


def validate_paths(args: argparse.Namespace) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    grafana_ini = pathlib.Path(args.grafana_ini)
    ldap_config = pathlib.Path(args.ldap_config)
    root_ca_cert = pathlib.Path(args.root_ca_cert)

    if not grafana_ini.exists():
        raise SystemExit(f"Grafana ini not found: {grafana_ini}")

    return grafana_ini, ldap_config, root_ca_cert


def resolve_ca_source(requested_path: pathlib.Path) -> pathlib.Path:
    if requested_path.exists():
        return requested_path

    for candidate in COMMON_CA_PATHS:
        candidate_path = pathlib.Path(candidate)
        if candidate_path.exists():
            print(f"Using cluster CA certificate from {candidate_path}")
            return candidate_path

    searched = ", ".join(COMMON_CA_PATHS)
    raise SystemExit(
        f"Cluster CA certificate not found: {requested_path}\n"
        f"Searched fallback locations: {searched}"
    )


def ensure_ca_available(source: pathlib.Path, destination: pathlib.Path, dry_run: bool) -> pathlib.Path:
    if source == destination and destination.exists():
        return destination

    print(f"Installing cluster CA certificate {source} -> {destination}")
    if dry_run:
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    os.chown(destination, pwd.getpwnam("root").pw_uid, grp.getgrnam("root").gr_gid)
    os.chmod(destination, 0o644)
    return destination


def restart_service(service_name: str, dry_run: bool) -> None:
    print(f"Restarting {service_name}")
    if dry_run:
        return
    subprocess.run(["systemctl", "restart", service_name], check=True)


def main() -> int:
    args = parse_args()
    require_root()

    grafana_ini, ldap_config, root_ca_cert = validate_paths(args)
    resolved_ca_source = resolve_ca_source(root_ca_cert)
    if not args.dry_run:
        ensure_ca_available(resolved_ca_source, root_ca_cert, args.dry_run)

    resolved_controller_ip = ensure_hosts_alias(
        pathlib.Path(args.hosts_path), args.ldap_host, args.controller_ip, args.dry_run
    )
    ensure_host_resolves(args.ldap_host, expected_ip=resolved_controller_ip or args.controller_ip)

    backup_file(grafana_ini, args.dry_run)
    if ldap_config.exists():
        backup_file(ldap_config, args.dry_run)

    update_grafana_ini(grafana_ini, str(ldap_config), args.dry_run)
    ldap_content = render_ldap_toml(args)
    atomic_write(ldap_config, ldap_content, "root", args.grafana_group, 0o640, args.dry_run)
    validate_file_metadata(ldap_config, "root", args.grafana_group, 0o640, args.dry_run)

    if args.restart:
        restart_service(args.service_name, args.dry_run)

    if not args.dry_run:
        validate_tls(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
