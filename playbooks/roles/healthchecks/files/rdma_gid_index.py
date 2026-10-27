#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys
from ipaddress import IPv6Address, ip_address

from shared_logging import logger

GID_INDEX = "3"
EXPECTED_GID_TYPE = "RoCE v2"
ZERO_GID = "0000:0000:0000:0000:0000:0000:0000:0000"

GID_CHECK_SHAPES = {
    "BM.GPU.H100.8",
    "BM.GPU.H200.8",
    "BM.GPU.B200.8",
    "BM.GPU.B300.8",
    "BM.GPU.B300.HS.8",
    "BM.GPU.GB200.4",
    "BM.GPU.GB200-v2.4",
    "BM.GPU.GB200-v3.4",
    "BM.GPU.GB300.4",
    "BM.GPU.MI355X-v1.8",
}


def numeric_suffix_sort_key(name):
    match = re.search(r"(\d+)$", name)
    if match:
        return int(match.group(1))
    return name


def list_matching(path, pattern):
    try:
        names = os.listdir(path)
    except (FileNotFoundError, OSError):
        return []
    return sorted([name for name in names if re.match(pattern, name)], key=numeric_suffix_sort_key)


def get_global_ip_addresses(interface):
    result = subprocess.run(
        ["ip", "-j", "addr", "show", "dev", interface],
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or f"Failed to inspect addresses for {interface}")

    addresses = []
    for entry in json.loads(result.stdout.strip() or "[]"):
        for addr in entry.get("addr_info", []):
            if addr.get("family") in ("inet", "inet6") and addr.get("scope") == "global":
                local = addr.get("local")
                if local:
                    addresses.append(local)
    return addresses


def gid_matches_ip(gid, address):
    try:
        gid_address = IPv6Address(gid.split("%", 1)[0])
        target_address = ip_address(address.split("%", 1)[0])
    except ValueError:
        return False

    if target_address.version == 4:
        return gid_address.ipv4_mapped == target_address
    return gid_address == target_address


def validate_gid_index(device, expected_netdev):
    port_path = os.path.join("/sys/class/infiniband", device, "ports", "1")
    if not os.path.isdir(port_path):
        return [f"{device}: missing RDMA port 1"]

    try:
        with open(os.path.join(port_path, "gids", GID_INDEX), "r", encoding="utf-8") as gid_file:
            gid = gid_file.read().strip()
        with open(os.path.join(port_path, "gid_attrs", "types", GID_INDEX), "r", encoding="utf-8") as gid_type_file:
            gid_type = gid_type_file.read().strip()
        with open(os.path.join(port_path, "gid_attrs", "ndevs", GID_INDEX), "r", encoding="utf-8") as netdev_file:
            netdev = netdev_file.read().strip()
    except (FileNotFoundError, OSError) as e:
        return [f"{device}: failed to read gid index {GID_INDEX} attributes: {e}"]

    issues = []

    if not gid or gid == ZERO_GID:
        issues.append(f"{device}: gid index {GID_INDEX} is empty")
    if not gid_type:
        issues.append(f"{device}: missing gid type for index {GID_INDEX}")
    elif gid_type != EXPECTED_GID_TYPE:
        issues.append(f"{device}: gid index {GID_INDEX} type is {gid_type}; expected {EXPECTED_GID_TYPE}")
    if netdev != expected_netdev:
        issues.append(f"{device}: gid index {GID_INDEX} maps to netdev {netdev}; expected {expected_netdev}")

    try:
        addresses = get_global_ip_addresses(expected_netdev)
    except RuntimeError as e:
        addresses = []
        issues.append(f"{expected_netdev}: failed to inspect global IP addresses: {e}")

    if not addresses:
        issues.append(f"{expected_netdev}: no global IP address")
    elif not any(gid_matches_ip(gid, address) for address in addresses):
        issues.append(f"{device}: gid index {GID_INDEX} gid {gid} does not match {expected_netdev} addresses: {addresses}")

    logger.debug(f"{device}: gid_index={GID_INDEX} type={gid_type} netdev={netdev} gid={gid}")
    return issues


def rdma_devices_for_netdev(netdev, infiniband_devices):
    devices = set()
    ib_device_path = os.path.join("/sys/class/net", netdev, "device", "infiniband")
    try:
        devices.update(os.listdir(ib_device_path))
    except (FileNotFoundError, OSError):
        pass

    for device in infiniband_devices:
        netdev_path = os.path.join("/sys/class/infiniband", device, "device", "net", netdev)
        if os.path.exists(netdev_path):
            devices.add(device)

    return sorted(devices, key=numeric_suffix_sort_key)


def add_expected_name_issues(issues, kind, expected, existing):
    missing = [name for name in expected if name not in existing]
    extra = [name for name in existing if name not in expected]
    if missing:
        issues.append(f"missing {kind}: " + ", ".join(missing))
    if extra:
        issues.append(f"unexpected {kind}: " + ", ".join(extra))


def check_rdma_gid_index(shape, expected_interface_count=None):
    if shape not in GID_CHECK_SHAPES:
        logger.info("RDMA GID Index Check: Skipped for shape " + shape)
        return []

    issues = []
    vf_rails = list_matching("/sys/class/infiniband", r"^rdma_vf_rail\d+$")
    rdma_netdevs = list_matching("/sys/class/net", r"^rdma\d+$")
    infiniband_devices = list_matching("/sys/class/infiniband", r".+")

    if vf_rails:
        logger.debug("RDMA GID Index Check: Checking rdma_vf_rail backend")
        if expected_interface_count is not None:
            expected_rails = [f"rdma_vf_rail{i}" for i in range(expected_interface_count)]
            add_expected_name_issues(issues, "RDMA VF rails", expected_rails, vf_rails)
        for rail in vf_rails:
            issues.extend(validate_gid_index(rail, rail))
    elif rdma_netdevs:
        logger.debug("RDMA GID Index Check: Checking classic rdma netdev backend")
        if expected_interface_count is not None:
            expected_netdevs = [f"rdma{i}" for i in range(expected_interface_count)]
            add_expected_name_issues(issues, "RDMA netdevs", expected_netdevs, rdma_netdevs)
        for netdev in rdma_netdevs:
            devices = rdma_devices_for_netdev(netdev, infiniband_devices)
            if not devices:
                issues.append(f"{netdev}: no RDMA device found for this netdev")
                continue
            if len(devices) > 1:
                issues.append(f"{netdev}: multiple RDMA devices found for this netdev: {', '.join(devices)}")

            for device in devices:
                issues.extend(validate_gid_index(device, netdev))
    else:
        issues.append("no RDMA VF rail or classic rdma netdev backend found")

    if issues:
        logger.warning("RDMA GID Index Check: Failed")
    else:
        logger.info("RDMA GID Index Check: Passed")
    return issues


def main():
    parser = argparse.ArgumentParser(description="Check RDMA gid index configuration")
    parser.add_argument("--shape", required=True, help="OCI shape name")
    parser.add_argument("--expected-interface-count", type=int,
                        help="Also check interface completeness; otherwise validate all discovered RDMA interfaces")
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO")
    args = parser.parse_args()

    logger.setLevel(args.log_level)
    issues = check_rdma_gid_index(args.shape, args.expected_interface_count)
    for issue in issues:
        logger.error("RDMA GID index issues: " + issue)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
