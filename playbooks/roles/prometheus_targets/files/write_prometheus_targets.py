#!/usr/bin/env python3
import argparse
import json
import os
import pwd
import grp
import tempfile
from pathlib import Path


ROLE_PORTS = {
    "controller": "controller_ports",
    "login": "login_ports",
    "compute": "compute_ports",
}


def target_payload(node, labels_map, ports):
    labels = {}
    for node_attr, prom_label in labels_map.items():
        value = node.get(node_attr)
        if value is not None:
            labels[prom_label] = str(value)

    shape = node.get("shape")
    if shape and "GPU" in shape:
        labels["vendor"] = "amd" if "BM.GPU.MI" in shape else "nvidia"

    hostname = node["hostname"]
    return [
        {
            "labels": labels,
            "targets": [f"{hostname}:{port}" for port in ports],
        }
    ]


def write_if_changed(path, content, uid, gid, mode):
    encoded = content.encode("utf-8")
    try:
        if path.read_bytes() == encoded:
            os.chown(path, uid, gid)
            os.chmod(path, mode)
            return False
    except FileNotFoundError:
        pass

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(encoded)
        os.chown(tmp_name, uid, gid)
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
    return True


def main():
    parser = argparse.ArgumentParser(description="Write Prometheus file_sd targets.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--targets-dir", required=True, type=Path)
    parser.add_argument("--user", required=True)
    parser.add_argument("--group", required=True)
    parser.add_argument("--mode", default="0775")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as input_file:
        config = json.load(input_file)

    args.targets_dir.mkdir(parents=True, exist_ok=True)

    uid = pwd.getpwnam(args.user).pw_uid
    gid = grp.getgrnam(args.group).gr_gid
    mode = int(args.mode, 8)

    all_hosts = config.get("all_hosts_info", {})
    labels_map = config.get("prometheus_labels", {})
    ports_by_role = {
        "controller": config.get("controller_ports", []),
        "login": config.get("login_ports", []),
        "compute": config.get("compute_ports", []),
    }

    desired = {}
    for node in all_hosts.values():
        role = node.get("role")
        if role not in ROLE_PORTS:
            continue
        if node.get("controller_status") == "terminating":
            continue
        hostname = node.get("hostname")
        if not hostname:
            continue

        payload = target_payload(node, labels_map, ports_by_role[role])
        desired[f"{hostname}.json"] = json.dumps(payload, indent=2, sort_keys=True) + "\n"

    changed = 0
    for filename, content in desired.items():
        if write_if_changed(args.targets_dir / filename, content, uid, gid, mode):
            changed += 1

    removed = 0
    for path in args.targets_dir.glob("*.json"):
        if path.name not in desired:
            path.unlink()
            removed += 1

    os.chown(args.targets_dir, uid, gid)
    os.chmod(args.targets_dir, mode)
    print(f"prometheus targets: desired={len(desired)} changed={changed} removed={removed}")


if __name__ == "__main__":
    main()
