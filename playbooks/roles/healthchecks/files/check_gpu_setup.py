#!/usr/bin/env python3
# /// script
# dependencies = [
#   "requests",
#   "psutil",
#   "distro"
# ]
# ///

"""
===========================================================================================
This is a Health Check script which covered below in order:
===========================================================================================
1. OCA (Oracle Cloud Agent) Status check
1.5. RDMA OCA Plugins Check
2. OCA Version Check
3. RTTCC (Round Trip Time Congestion Control) Status Check
4. ECC (Error-Correcting Code) Errors Check**:
5. Row Remap Errors Check
6. GPU Count Check
7. GPU PCIe Link Width Check
8. GPU Bandwidth Test
9. Bus Status Check
10. RDMA Link Status Check
11. RDMA Link Flapping Check
11.5. NVIDIA IMEX Service Readiness Check
12. GPU Xid Errors Check
13. WPA Authentication Check
14. Fabric Manager Status Check
15. CPU Performance Profile Check
16. Pending Bad Pages Check (AMD GPUs)
17. Check if all interfaces have an IP address
18. Check NVLinks speeds
19. Run dcgmi health check
20. Run rocminfo check (AMD GPUs)
21. Run LBNL NHC


===========================================================================================
Usage:
===========================================================================================
- The script will perform all health checks by default except bandwidth test.
- The script can be run with specific arguments to perform individual checks.
  Example: `python3 check_gpu_setup.py --gpucount` (runs only the GPU count check).
  Use the `--help` flag to see all available options.

===========================================================================================
"""

import subprocess
import csv
import re
import argparse
from gpu_bw_test import BandwidthTest
from rdma_link_flapping import LinkFlappingTest
from xid_checker import XidChecker
import platform
import os
import requests
import json
import time
import sys
import socket
import psutil
import ipaddress
from pathlib import Path

version = sys.version_info
if version >= (3, 12):
    from datetime import datetime, timedelta, UTC
else:
    from datetime import datetime, timedelta


from shared_logging import logger

SMI_TIMEOUT_SEC = 10

RDMA_SHAPE_DEVICES = {
    "BM.GPU.H100.8": ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
    "BM.GPU.H200.8": ["mlx5_0", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_9", "mlx5_10", "mlx5_11"],
    "BM.GPU.B200.8": ["mlx5_0", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_9", "mlx5_10", "mlx5_11"],
    "BM.GPU.B300.8": ["mlx5_0", "mlx5_1", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_16", "mlx5_17", "mlx5_18", "mlx5_19", "mlx5_20", "mlx5_21"],
    "BM.GPU.B300.HS.8": ["mlx5_0", "mlx5_1", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_16", "mlx5_17", "mlx5_18", "mlx5_19", "mlx5_20", "mlx5_21"],
    "BM.GPU.GB200.4": ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4"],
    "BM.GPU.GB200-v2.4": ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4"],
    "BM.GPU.GB200-v3.4": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8"],
    "BM.GPU.GB300.4": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8"],
    "BM.GPU.B4.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
    "BM.GPU.A100-v2.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
    "BM.GPU4.8": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
    "BM.GPU.MI300X.8": ["mlx5_0", "mlx5_2", "mlx5_3","mlx5_4", "mlx5_5", "mlx5_7", "mlx5_8", "mlx5_9"],
    "BM.GPU.MI355X-v1.8": ["mlx5_0", "mlx5_1", "mlx5_2","mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7"]
}

MLXLINK_MULTI_PLANE_SHAPE_DEVICES = {
    "BM.GPU.GB300.4": ["/dev/fwctl/fwctl0", "/dev/fwctl/fwctl1", "/dev/fwctl/fwctl2", "/dev/fwctl/fwctl3", "/dev/fwctl/fwctl4", "/dev/fwctl/fwctl5", "/dev/fwctl/fwctl6", "/dev/fwctl/fwctl7", "/dev/fwctl/fwctl9", "/dev/fwctl/fwctl10", "/dev/fwctl/fwctl11", "/dev/fwctl/fwctl12", "/dev/fwctl/fwctl13", "/dev/fwctl/fwctl14", "/dev/fwctl/fwctl15", "/dev/fwctl/fwctl16"],
    "BM.GPU.B300.8": [
        "/dev/fwctl/fwctl0", "/dev/fwctl/fwctl1", "/dev/fwctl/fwctl2", "/dev/fwctl/fwctl3",
        "/dev/fwctl/fwctl9", "/dev/fwctl/fwctl10", "/dev/fwctl/fwctl11", "/dev/fwctl/fwctl12",
        "/dev/fwctl/fwctl13", "/dev/fwctl/fwctl14", "/dev/fwctl/fwctl15", "/dev/fwctl/fwctl16",
        "/dev/fwctl/fwctl17", "/dev/fwctl/fwctl18", "/dev/fwctl/fwctl19", "/dev/fwctl/fwctl20",
        "/dev/fwctl/fwctl21", "/dev/fwctl/fwctl22", "/dev/fwctl/fwctl23", "/dev/fwctl/fwctl24",
        "/dev/fwctl/fwctl26", "/dev/fwctl/fwctl27", "/dev/fwctl/fwctl28", "/dev/fwctl/fwctl29",
        "/dev/fwctl/fwctl30", "/dev/fwctl/fwctl31", "/dev/fwctl/fwctl32", "/dev/fwctl/fwctl33",
        "/dev/fwctl/fwctl34", "/dev/fwctl/fwctl35", "/dev/fwctl/fwctl36", "/dev/fwctl/fwctl37",
    ],
    "BM.GPU.B300.HS.8": [
        "/dev/fwctl/fwctl0", "/dev/fwctl/fwctl1", "/dev/fwctl/fwctl2", "/dev/fwctl/fwctl3",
        "/dev/fwctl/fwctl9", "/dev/fwctl/fwctl10", "/dev/fwctl/fwctl11", "/dev/fwctl/fwctl12",
        "/dev/fwctl/fwctl13", "/dev/fwctl/fwctl14", "/dev/fwctl/fwctl15", "/dev/fwctl/fwctl16",
        "/dev/fwctl/fwctl17", "/dev/fwctl/fwctl18", "/dev/fwctl/fwctl19", "/dev/fwctl/fwctl20",
        "/dev/fwctl/fwctl21", "/dev/fwctl/fwctl22", "/dev/fwctl/fwctl23", "/dev/fwctl/fwctl24",
        "/dev/fwctl/fwctl26", "/dev/fwctl/fwctl27", "/dev/fwctl/fwctl28", "/dev/fwctl/fwctl29",
        "/dev/fwctl/fwctl30", "/dev/fwctl/fwctl31", "/dev/fwctl/fwctl32", "/dev/fwctl/fwctl33",
        "/dev/fwctl/fwctl34", "/dev/fwctl/fwctl35", "/dev/fwctl/fwctl36", "/dev/fwctl/fwctl37",
    ],
}

SHAPES_WITHOUT_IP_ADDRESS_CHECK = {"BM.GPU.GB200.4"}
SHAPES_WITHOUT_OCA_STATE_CHECK = {
    "BM.GPU.GB200.4",
    "BM.GPU.L40S-NC.4",
    "BM.GPU.A10.4",
}

MULTIPLANAR_RDMA_VF_COUNTS = {
    "BM.GPU.GB300.4": 4,
    "BM.GPU.B300.8": 8,
    "BM.GPU.B300.HS.8": 8,
}

MULTIPLANAR_RDMA_VF_ADDRESS_MINIMUM_ONLY = {
    "BM.GPU.GB300.4": False,
    "BM.GPU.B300.8": True,
    "BM.GPU.B300.HS.8": True,
}


RDMA_VF_LOG_COUNTERS = (
    "req_cqe_error",
    "req_cqe_flush_error",
    "req_remote_access_errors",
    "resp_cqe_error",
    "resp_cqe_flush_error",
)

MULTIPLANAR_OVS_RDMA_CONFIG = {
    "BM.GPU.B300.8": {
        "ovs_mtu": 9216,
        "bridge_kernel_mtu": 9216,
        "dpdk_kernel_mtu": [9216, 9266],
        "dpdk_mtu_request": 9216,
        "dpdk_max_rx_pktlen": 9234,
        "rails": 8,
        "planes": 4,
    },
    "BM.GPU.B300.HS.8": {
        "ovs_mtu": 9216,
        "bridge_kernel_mtu": 9216,
        "dpdk_kernel_mtu": [9216, 9266],
        "dpdk_mtu_request": 9216,
        "dpdk_max_rx_pktlen": 9234,
        "rails": 8,
        "planes": 4,
    },
    "BM.GPU.GB300.4": {
        "ovs_mtu": 9216,
        "bridge_kernel_mtu": 9216,
        "dpdk_kernel_mtu": [9216, 9266],
        "dpdk_mtu_request": 9216,
        "dpdk_max_rx_pktlen": 9234,
        "rails": 4,
        "planes": 4,
    },
}

#Section 0: Common Functions for all Health Checks.
###################################################

# Make a request to metadata endpoint
def get_metadata():
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()

def get_instance_plugins():
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/agentConfig/pluginsConfig"
    response = requests.get(request_url, headers=headers)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    return response.json()

def get_host_metadata():
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/host"
    response = requests.get(request_url, headers=headers)
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return response.json()

def get_rdma_planes():
    default_planes = 1
    try:
        host_metadata = get_host_metadata()
    except (requests.RequestException, ValueError) as e:
        logger.debug(f"Could not read host metadata RDMA fabric data: {e}")
        return default_planes

    if not isinstance(host_metadata, dict):
        return default_planes

    rdma_fabric_data = host_metadata.get("rdmaFabricData", {})
    if not isinstance(rdma_fabric_data, dict):
        return default_planes

    try:
        return int(rdma_fabric_data.get("planes", default_planes))
    except (TypeError, ValueError):
        logger.debug(f"Invalid rdmaFabricData.planes value: {rdma_fabric_data.get('planes')}")
        return default_planes

def is_multiplanar(shape):
    return get_rdma_planes() > 1

def get_multiplanar_rdma_vf_count(shape):
    try:
        return MULTIPLANAR_RDMA_VF_COUNTS[shape]
    except KeyError:
        raise ValueError(f"Unsupported MultiPlanar RDMA VF shape: {shape}")

def allows_multiple_multiplanar_rdma_vf_addresses(shape):
    try:
        return MULTIPLANAR_RDMA_VF_ADDRESS_MINIMUM_ONLY[shape]
    except KeyError:
        raise ValueError(f"Unsupported MultiPlanar RDMA VF address policy shape: {shape}")

def rdma_rail_sort_key(device):
    match = re.search(r'(\d+)$', device)
    if match:
        return int(match.group(1))
    return device

def rdma_plane_rail_sort_key(interface):
    match = re.match(r'^rdma_p(\d+)_rail(\d+)$', interface)
    if match:
        plane, rail = match.groups()
        return (int(rail), int(plane))
    return (sys.maxsize, interface)

def rdma_plane_rail_parts(interface):
    match = re.match(r'^rdma_p(\d+)_rail(\d+)$', interface)
    if match:
        plane, rail = match.groups()
        return int(plane), int(rail)
    return None

def discover_multiplanar_rdma_devices(shape):
    infiniband_dir = "/sys/class/infiniband"
    try:
        devices = os.listdir(infiniband_dir)
    except FileNotFoundError:
        devices = []

    vf_rails = [device for device in devices if re.match(r'^rdma_vf_rail\d+$', device)]
    if vf_rails:
        return sorted(vf_rails, key=rdma_rail_sort_key)

    return [f"rdma_vf_rail{i}" for i in range(get_multiplanar_rdma_vf_count(shape))]

def discover_multiplanar_wpa_interfaces(shape):
    try:
        interfaces = os.listdir("/sys/class/net")
    except FileNotFoundError:
        interfaces = []

    wpa_interfaces = [
        interface for interface in interfaces
        if re.match(r'^rdma_p\d+_rail\d+$', interface)
    ]
    if wpa_interfaces:
        return sorted(wpa_interfaces, key=rdma_plane_rail_sort_key)

    planes = get_rdma_planes()
    rails = get_multiplanar_rdma_vf_count(shape)
    return [
        f"rdma_p{plane}_rail{rail}"
        for rail in range(rails)
        for plane in range(planes)
    ]


def pci_function_base(path):
    real_path = os.path.realpath(path)
    return re.sub(r'\.\d+$', '', real_path)

def discover_multiplanar_mlxlink_fwctl_devices():
    fwctl_dir = "/sys/class/fwctl"
    infiniband_dir = "/sys/class/infiniband"
    try:
        infiniband_devices = os.listdir(infiniband_dir)
        fwctl_devices = os.listdir(fwctl_dir)
    except FileNotFoundError:
        return []

    rail_bases = set()
    for device in infiniband_devices:
        if re.match(r'^rdma_rail\d+$', device):
            rail_bases.add(pci_function_base(os.path.join(infiniband_dir, device, "device")))

    devices = []
    for device in fwctl_devices:
        device_path = os.path.join(fwctl_dir, device, "device")
        real_path = os.path.realpath(device_path)
        function_match = re.search(r'\.(\d+)$', real_path)
        if not function_match or int(function_match.group(1)) >= 4:
            continue
        if pci_function_base(device_path) in rail_bases:
            devices.append(os.path.join("/dev/fwctl", device))

    return sorted(devices, key=rdma_rail_sort_key)


def _run_ip_json(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        command_text = " ".join(command)
        raise RuntimeError(stderr or "Command failed: " + command_text)

    output = result.stdout.strip()
    if not output:
        return []

    try:
        return json.loads(output)
    except json.JSONDecodeError as e:
        command_text = " ".join(command)
        raise RuntimeError("Could not parse JSON from " + command_text + ": " + str(e))


def _get_global_ipv6_addresses(interface):
    data = _run_ip_json(["ip", "-j", "-6", "addr", "show", "dev", interface])
    addresses = []
    for entry in data:
        for addr in entry.get("addr_info", []):
            if addr.get("family") == "inet6" and addr.get("scope") == "global":
                local = addr.get("local")
                if local:
                    addresses.append(local)
    return addresses


def _get_link_local_ipv6_addresses(interface):
    data = _run_ip_json(["ip", "-j", "-6", "addr", "show", "dev", interface])
    addresses = []
    for entry in data:
        for addr in entry.get("addr_info", []):
            if addr.get("family") == "inet6" and addr.get("scope") == "link":
                local = addr.get("local")
                if local:
                    addresses.append(local)
    return addresses


def ipv6_address_value(address):
    return int(ipaddress.IPv6Address(address.split("%", 1)[0]))


def _get_ipv6_default_routes_for_interface(interface):
    data = _run_ip_json(["ip", "-j", "-6", "route", "show", "default", "dev", interface, "table", "all"])
    return [route for route in data if route.get("dst") == "default"]


def check_multiplanar_rdma_rail_ipv6_sequence(metadata):
    shape = metadata.get("shape", "")
    if not is_multiplanar(shape):
        logger.info("RDMA rail IPv6 Sequence Check: Skipped for non-MultiPlanar shape")
        return []

    issues = []
    interfaces = discover_multiplanar_wpa_interfaces(shape)
    expected_planes = get_rdma_planes()
    expected_rails = get_multiplanar_rdma_vf_count(shape)
    expected_interface_count = expected_planes * expected_rails

    if len(interfaces) != expected_interface_count:
        issues.append(
            "Expected " + str(expected_interface_count) +
            " rdma_p<plane>_rail<rail> interfaces, found " +
            str(len(interfaces)) + ": " + str(interfaces)
        )

    addresses_by_rail = {}
    for interface in interfaces:
        parts = rdma_plane_rail_parts(interface)
        if not parts:
            continue

        plane, rail = parts
        try:
            addresses = _get_link_local_ipv6_addresses(interface)
        except RuntimeError as e:
            issues.append(interface + ": failed to inspect link-local IPv6 addresses: " + str(e))
            continue

        if len(addresses) != 1:
            issues.append(
                interface + ": expected exactly one link-local IPv6 address, found " +
                str(len(addresses)) + ": " + str(addresses)
            )
            continue

        try:
            address_value = ipv6_address_value(addresses[0])
        except ValueError as e:
            issues.append(interface + ": invalid link-local IPv6 address " + addresses[0] + ": " + str(e))
            continue

        addresses_by_rail.setdefault(rail, {})[plane] = {
            "interface": interface,
            "address": addresses[0],
            "value": address_value,
        }

    for rail in range(expected_rails):
        plane_addresses = addresses_by_rail.get(rail, {})
        missing_planes = [
            plane for plane in range(expected_planes)
            if plane not in plane_addresses
        ]
        if missing_planes:
            issues.append(
                "rail" + str(rail) + ": missing link-local IPv6 addresses for plane(s) " +
                str(missing_planes)
            )

        sorted_planes = sorted(plane_addresses)
        for i in range(1, len(sorted_planes)):
            previous_plane = sorted_planes[i - 1]
            current_plane = sorted_planes[i]
            previous = plane_addresses[previous_plane]
            current = plane_addresses[current_plane]
            expected_delta = current_plane - previous_plane
            actual_delta = current["value"] - previous["value"]
            if actual_delta != expected_delta:
                issues.append(
                    "rail" + str(rail) + ": link-local IPv6 addresses are not sequential between " +
                    previous["interface"] + " (" + previous["address"] + ") and " +
                    current["interface"] + " (" + current["address"] + "); expected +" +
                    str(expected_delta) + ", found " + str(actual_delta)
                )

    if issues:
        logger.warning("RDMA rail IPv6 Sequence Check: Failed")
    else:
        logger.info("RDMA rail IPv6 Sequence Check: Passed")

    return issues


def check_multiplanar_rdma_vf_routes(metadata):
    shape = metadata.get("shape", "")
    if not is_multiplanar(shape):
        logger.info("RDMA VF Route Check: Skipped for non-MultiPlanar shape")
        return []

    issues = []
    interfaces = discover_multiplanar_rdma_devices(shape)
    expected_rails = get_multiplanar_rdma_vf_count(shape)

    if len(interfaces) != expected_rails:
        issues.append(
            "Expected " + str(expected_rails) + " rdma_vf_rail interfaces, found " +
            str(len(interfaces)) + ": " + str(interfaces)
        )

    for interface in interfaces:
        try:
            addresses = _get_global_ipv6_addresses(interface)
        except RuntimeError as e:
            issues.append(interface + ": failed to inspect IPv6 addresses: " + str(e))
            addresses = []

        if allows_multiple_multiplanar_rdma_vf_addresses(shape):
            if len(addresses) < 1:
                issues.append(
                    interface + ": expected at least one global IPv6 address, found none"
                )
        elif len(addresses) != 1:
            issues.append(
                interface + ": expected exactly one global IPv6 address, found " +
                str(len(addresses)) + ": " + str(addresses)
            )

        try:
            routes = _get_ipv6_default_routes_for_interface(interface)
        except RuntimeError as e:
            issues.append(interface + ": failed to inspect IPv6 default routes: " + str(e))
            routes = []

        if len(routes) != 1:
            route_summary = []
            for route in routes:
                route_summary.append(
                    "table=" + str(route.get("table", "main")) +
                    " gateway=" + str(route.get("gateway", "none")) +
                    " proto=" + str(route.get("protocol", "none"))
                )
            issues.append(
                interface + ": expected exactly one IPv6 default route bound to " +
                interface + " in table all, found " + str(len(routes)) + ": " + str(route_summary)
            )

    if issues:
        logger.warning("RDMA VF Route Check: Failed")
    else:
        logger.info("RDMA VF Route Check: Passed")

    return issues

def check_multiplanar_rdma_vf_counters(metadata):
    shape = metadata.get("shape", "")
    if not is_multiplanar(shape):
        logger.info("RDMA VF Counter Check: Skipped for non-MultiPlanar shape")
        return []

    issues = []
    counter_values = []
    for device in discover_multiplanar_rdma_devices(shape):
        device_name = os.path.basename(device)
        for counter in RDMA_VF_LOG_COUNTERS:
            counter_path = os.path.join(
                "/sys/class/infiniband",
                device_name,
                "ports",
                "1",
                "hw_counters",
                counter,
            )
            if not os.path.isfile(counter_path):
                continue
            try:
                with open(counter_path, "r") as counter_file:
                    value = int(counter_file.read().strip())
            except (OSError, ValueError) as e:
                logger.warning(device_name + " " + counter + ": failed to read counter: " + str(e))
                continue

            counter_values.append(device_name + " " + counter + "=" + str(value))

    if issues:
        logger.warning("RDMA VF Counter Check: Failed")
    else:
        if counter_values:
            logger.debug("RDMA VF Counter Check values: " + "; ".join(counter_values))
        logger.info("RDMA VF Counter Check: Passed")

    return issues


def _parse_optional_int(value):
    value = str(value).strip()
    if value in ("", "[]", "None"):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _expected_values(value):
    if isinstance(value, (list, tuple, set)):
        return tuple(value)
    return (value,)


def _format_expected_values(values):
    return " or ".join(str(value) for value in values)


def _get_netdev_mtu(interface):
    mtu_path = os.path.join("/sys/class/net", interface, "mtu")
    if not os.path.isfile(mtu_path):
        return None
    try:
        with open(mtu_path, "r") as mtu_file:
            return int(mtu_file.read().strip())
    except (OSError, ValueError):
        return None


def _get_ovs_interface_state():
    command = [
        "ovs-vsctl",
        "--format=csv",
        "--data=bare",
        "--no-headings",
        "--columns=name,type,mtu,mtu_request,status",
        "list",
        "Interface",
    ]
    if not is_user_root():
        command = ["sudo", "-n"] + command
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise RuntimeError("ovs-vsctl not found")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ovs-vsctl timed out")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(stderr or "ovs-vsctl Interface query failed")

    state = {}
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) < 5:
            continue
        name, interface_type, mtu, mtu_request, status = row[:5]
        max_rx_pktlen = None
        match = re.search(r'(?:^| )max_rx_pktlen=(\d+)(?: |$)', status)
        if match:
            max_rx_pktlen = int(match.group(1))
        state[name] = {
            "type": interface_type,
            "mtu": _parse_optional_int(mtu),
            "mtu_request": _parse_optional_int(mtu_request),
            "max_rx_pktlen": max_rx_pktlen,
        }
    return state


def _format_interface_list(interfaces, limit=12):
    if len(interfaces) <= limit:
        return ", ".join(interfaces)
    return ", ".join(interfaces[:limit]) + ", ... (" + str(len(interfaces)) + " total)"


def check_multiplanar_rdma_ovs_mtu(metadata):
    shape = metadata.get("shape", "")
    config = MULTIPLANAR_OVS_RDMA_CONFIG.get(shape)
    if config is None or not is_multiplanar(shape):
        logger.info("RDMA OVS MTU Check: Skipped for non-B300/GB300 MultiPlanar shape")
        return []

    issues = []
    expected_ovs_mtu = config["ovs_mtu"]
    expected_bridge_kernel_mtu = config.get("bridge_kernel_mtu", expected_ovs_mtu)
    expected_dpdk_kernel_mtu_values = _expected_values(
        config.get("dpdk_kernel_mtu", expected_ovs_mtu)
    )
    expected_dpdk_mtu_request = config.get("dpdk_mtu_request", expected_ovs_mtu)
    expected_dpdk_max_rx_pktlen = config.get("dpdk_max_rx_pktlen", expected_ovs_mtu + 18)
    expected_rails = config["rails"]
    expected_planes = max(get_rdma_planes(), config["planes"])

    bridge_interfaces = [
        "br-rail" + str(rail)
        for rail in range(expected_rails)
    ]
    dpdk_interfaces = [
        "rdma" + str(rail)
        for rail in range(expected_rails)
    ]
    dpdk_interfaces.extend(
        "rdma_p" + str(plane) + "_rail" + str(rail)
        for rail in range(expected_rails)
        for plane in range(expected_planes)
    )

    try:
        ovs_state = _get_ovs_interface_state()
    except RuntimeError as e:
        issues.append("failed to inspect OVS Interface table: " + str(e))
        logger.warning("RDMA OVS MTU Check: Failed")
        return issues

    missing_ovs_interfaces = []
    bad_bridge_interfaces = []
    bad_dpdk_interfaces = []

    for interface in bridge_interfaces:
        state = ovs_state.get(interface)
        kernel_mtu = _get_netdev_mtu(interface)
        if state is None:
            missing_ovs_interfaces.append(interface)
            continue

        interface_issues = []
        if state["type"] != "internal":
            interface_issues.append("type=" + str(state["type"]) + " expected internal")
        if state["mtu"] != expected_ovs_mtu:
            interface_issues.append("ovs_mtu=" + str(state["mtu"]) + " expected " + str(expected_ovs_mtu))
        if kernel_mtu != expected_bridge_kernel_mtu:
            interface_issues.append("kernel_mtu=" + str(kernel_mtu) + " expected " + str(expected_bridge_kernel_mtu))

        if interface_issues:
            bad_bridge_interfaces.append(interface + "(" + ", ".join(interface_issues) + ")")

    for interface in dpdk_interfaces:
        state = ovs_state.get(interface)
        kernel_mtu = _get_netdev_mtu(interface)
        if state is None:
            missing_ovs_interfaces.append(interface)
            continue

        interface_issues = []
        if state["type"] != "dpdk":
            interface_issues.append("type=" + str(state["type"]) + " expected dpdk")
        if state["mtu"] != expected_ovs_mtu:
            interface_issues.append("ovs_mtu=" + str(state["mtu"]) + " expected " + str(expected_ovs_mtu))
        if state["mtu_request"] != expected_dpdk_mtu_request:
            interface_issues.append("mtu_request=" + str(state["mtu_request"]) + " expected " + str(expected_dpdk_mtu_request))
        if state["max_rx_pktlen"] != expected_dpdk_max_rx_pktlen:
            interface_issues.append("max_rx_pktlen=" + str(state["max_rx_pktlen"]) + " expected " + str(expected_dpdk_max_rx_pktlen))
        if kernel_mtu not in expected_dpdk_kernel_mtu_values:
            interface_issues.append(
                "kernel_mtu=" + str(kernel_mtu) + " expected " +
                _format_expected_values(expected_dpdk_kernel_mtu_values)
            )

        if interface_issues:
            bad_dpdk_interfaces.append(interface + "(" + ", ".join(interface_issues) + ")")

    if missing_ovs_interfaces:
        issues.append("missing expected OVS RDMA interfaces: " + _format_interface_list(missing_ovs_interfaces))
    if bad_bridge_interfaces:
        issues.append(
            "br-rail MTU/runtime mismatch on " + str(len(bad_bridge_interfaces)) + "/" +
            str(len(bridge_interfaces)) + " interfaces: " + _format_interface_list(bad_bridge_interfaces, limit=8)
        )
    if bad_dpdk_interfaces:
        issues.append(
            "OVS DPDK RDMA MTU/runtime mismatch on " + str(len(bad_dpdk_interfaces)) + "/" +
            str(len(dpdk_interfaces)) + " interfaces: " + _format_interface_list(bad_dpdk_interfaces, limit=12)
        )

    if issues:
        logger.warning("RDMA OVS MTU Check: Failed")
    else:
        logger.info("RDMA OVS MTU Check: Passed")

    return issues

def check_imex_ready(metadata):
    shape = metadata.get("shape", "")
    if shape != "BM.GPU.GB300.4" or not is_multiplanar(shape):
        logger.info("IMEX Check: Skipped for non-GB300 MultiPlanar shape")
        return []

    issues = []

    try:
        service = subprocess.run(
            ["systemctl", "is-active", "--quiet", "nvidia-imex.service"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        issues.append("systemctl is-active nvidia-imex.service timed out")
    except FileNotFoundError:
        issues.append("systemctl command not found")
    else:
        if service.returncode != 0:
            stderr = service.stderr.strip()
            issue = "nvidia-imex.service is not active"
            if stderr:
                issue += ", stderr: " + stderr
            issues.append(issue)

    try:
        status = subprocess.run(
            ["nvidia-imex-ctl", "-q"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        issues.append("nvidia-imex-ctl -q timed out")
    except FileNotFoundError:
        issues.append("nvidia-imex-ctl command not found")
    else:
        stdout = status.stdout.strip()
        stderr = status.stderr.strip()
        if status.returncode != 0 or stdout != "READY":
            issue = "nvidia-imex-ctl -q returned code " + str(status.returncode)
            if stdout:
                issue += ", stdout: " + stdout
            if stderr:
                issue += ", stderr: " + stderr
            issues.append(issue)

    if issues:
        logger.warning("IMEX Check: Failed")
    else:
        logger.info("IMEX Check: Passed")

    return issues


# Check if the user is root
def is_user_root():
    if os.geteuid() != 0:
        logger.debug("User is not root!")
        return False
    return True

# Define Mellanox RDMA devices based on GPU shape.
def get_rdma_devices():
    metadata = get_metadata()
    shape = metadata['shape']

    if is_multiplanar(shape):
        output_devices = discover_multiplanar_rdma_devices(shape)
    else:
        output_devices = RDMA_SHAPE_DEVICES.get(shape, [])

    logger.debug(f"Using RDMA devices {output_devices}")
    return output_devices

# Define device names to pass to mlxlink. MultiPlanar GB300/B300 use fwctl names.
def get_mlxlink_devices():
    metadata = get_metadata()
    shape = metadata['shape']

    output_devices = RDMA_SHAPE_DEVICES.get(shape, [])
    if shape == "BM.GPU.B300.8" and is_multiplanar(shape):
        output_devices = discover_multiplanar_mlxlink_fwctl_devices()
        if not output_devices:
            output_devices = MLXLINK_MULTI_PLANE_SHAPE_DEVICES[shape]
    elif shape in MLXLINK_MULTI_PLANE_SHAPE_DEVICES and is_multiplanar(shape):
        output_devices = MLXLINK_MULTI_PLANE_SHAPE_DEVICES[shape]
    if shape == "BM.GPU.B300.HS.8" and is_multiplanar(shape):
        output_devices = discover_multiplanar_mlxlink_fwctl_devices()
        if not output_devices:
            output_devices = MLXLINK_MULTI_PLANE_SHAPE_DEVICES[shape]
    elif shape in MLXLINK_MULTI_PLANE_SHAPE_DEVICES and is_multiplanar(shape):
        output_devices = MLXLINK_MULTI_PLANE_SHAPE_DEVICES[shape]

    logger.debug(f"Using mlxlink devices {output_devices}")
    return output_devices

# Keep the old helper as the default mlxlink/register-device view.
def get_devices():
    return get_mlxlink_devices()

def should_check_ip_addresses(shape):
    return shape not in SHAPES_WITHOUT_IP_ADDRESS_CHECK

def has_rdma_interfaces():
    try:
        return len(os.listdir("/sys/class/infiniband")) > 0
    except OSError:
        return False

def is_link_local_ipv6_address(address):
    return address.split("%", 1)[0].lower().startswith("fe80:")

# Retrieve a unique host identifier and indicate if it's a VM or BM.
def get_host_serial():
    try:
        # Try dmidecode first (Only works on BM instances)
        cmd = ['sudo', 'dmidecode', '-s', 'system-serial-number'] if not is_user_root() else ['dmidecode', '-s', 'system-serial-number']
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        serial_number = result.stdout.decode('utf-8').strip()

        # If dmidecode output is empty, "Not Specified", or failed, assume it's a VM
        if result.returncode == 0 and serial_number and serial_number != "Not Specified":
            return f"BM Instance: {serial_number}"  # Bare metal instance serial number

    except (FileNotFoundError, ValueError):
        pass  # Continue to check for VM instance

    try:
        # Fallback: Get instance OCID from OCI metadata (for VM instances)
        instance_ocid = metadata.get("id", "Unknown")
        return f"VM Instance: {instance_ocid}"  # VM instance identifier

    except requests.RequestException:
        pass  # Metadata service not available

    return "Unknown Instance"  # Final fallback if all methods fail

# Initialize global variables for Slurm reasons and error count
slurm_drain_reason = []
slurm_error_count = 0

RDMA_SLURM_REASON_PRIORITY = (
    "RDMA Link down",
    "WPA Auth Error",
    "RDMA Route Missing",
    "RDMA Missing IP",
    "RDMA OVS MTU Error",
    "RDMA Rail IPv6 Sequence Error",
    "RDMA Link flap",
    "RDMA Auth flap",
)

# Function to provide slurm reason for a node to be drained or down
def slurm_reason(message):
    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason.append(message)
    slurm_error_count+=1

def format_healthcheck_status(reasons):
    unique_reasons = list(dict.fromkeys(reason for reason in reasons if reason))
    rdma_reason = next(
        (reason for reason in RDMA_SLURM_REASON_PRIORITY if reason in unique_reasons),
        None,
    )
    if rdma_reason:
        filtered_reasons = []
        added_rdma_reason = False
        for reason in unique_reasons:
            if reason in RDMA_SLURM_REASON_PRIORITY:
                if not added_rdma_reason:
                    filtered_reasons.append(rdma_reason)
                    added_rdma_reason = True
                continue
            filtered_reasons.append(reason)
        unique_reasons = filtered_reasons
    if unique_reasons:
        return ", ".join(unique_reasons)
    return "Healthy"

# Function to provide recommendation for any health issue found
def recommended_action(current, action):
    if action not in (None,"FabricManagerRestart","Reboot","Terminate","Wait_For_OCA","Reset_GPU","Check_nhc_log","Enable_Instance_RDMA_Plugins"):
        logger.error("No action was found")
        return 0
    if action in ("Reboot", "FabricManagerRestart", "Wait_For_OCA", "Reset_GPU", "Check_nhc_log"):
        if current == "Terminate":
            return current
    if action is None:
        return current
    if action == "Terminate":
        return action
    if action in ("Wait_For_OCA",):
        if current in ("FabricManagerRestart","Reboot","Terminate","Reset_GPU","Check_nhc_log"):
            return current
        else:
            return action
    if action in ("Check_nhc_log", "Enable_Instance_RDMA_Plugins"):
        if current in ("FabricManagerRestart","Reboot","Terminate","Reset_GPU"):
            return current
        else:
            return action
    return action

# Check the reboot counts
def get_reboots_count():
    result = subprocess.run(["last", "-x", "reboot"], stdout=subprocess.PIPE)
    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')
    now = datetime.now()
    one_day_ago = now - timedelta(hours=24)
    two_hours_ago = now - timedelta(hours=2)
    twelve_hours_ago = now - timedelta(hours=12)

    reboot_count_last_day = 0
    last_reboot_within_2hour = 0
    last_reboot_within_12hours = 0
    reboot_lines=[]
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] != "reboot":
            continue  # Ignore invalid lines
        reboot_lines.append(line)
    for line in reboot_lines[:-1]:
        parts = line.split()
        # Extract timestamp (format: "Mon Jan  1 12:34")
        date_str = " ".join(parts[4:8])  # Extract date/time part
        reboot_time = datetime.strptime(date_str, "%a %b %d %H:%M")
        reboot_time = reboot_time.replace(year=now.year)  # Assume current year
        # Count reboots in the last 24 hours
        if reboot_time >= one_day_ago:
            reboot_count_last_day += 1

        # Check if the last reboot was within the last 2 hours
        if reboot_time >= two_hours_ago:
            last_reboot_within_2hour += 1

        # Check if the last reboot was within the last 12 hours
        if reboot_time >= twelve_hours_ago:
            last_reboot_within_12hours += 1

    return reboot_count_last_day, last_reboot_within_2hour, last_reboot_within_12hours

# This function is called only when Xid error is present and when the remediation of the Xid is GPU reset.
# Check section 12.3 for details.
def gpu_reset_reboot(xc):

    # The below function checks
    #       Recently rebooted: Tag and terminate
    #       Not recently rebooted: GPU reset
    def gpu_reset_logic():
        number_of_reboots,last_2hour_reboot,last_12hour_reboot = get_reboots_count()
        if last_12hour_reboot > 0 or number_of_reboots > 3:
            # Tag and Terminate
            logger.error("Xid Error Check: Failed")
            return "Terminate", False
        else:
            # GPU reset
            logger.error("Xid Error Check: Failed")
            return "GPU_Reset", False

    # List of (index, line, timestamp) for lines that contain nvidia-nvswitch: Probing device. These are the lines that indicate a GPU Reset.
    gpu_reset_indices = []
    # List of indices for lines that contain NVRM: Xid
    xid_indices = []

    # Get the dmesg output
    dmesg_output = xc.get_dmesg()
    if dmesg_output == "":
        return "", True
    dmesg_lines = dmesg_output.splitlines()

    # get the indices of the lines with Xid error and GPU reset
    for idx, line in enumerate(dmesg_lines):
        if "nvidia-nvswitch: Probing device" in line:
            # Parse the timestamp for the lines that mention GPU has been reset.
            ts = XidChecker.parse_dmesg_timestamp(line)
            gpu_reset_indices.append((idx, line, ts))
        if "NVRM: Xid" in line:
            xid_indices.append(idx)

    gpu_reset_present = len(gpu_reset_indices) > 0
    now = datetime.now()

    # Get all the GPU resets in the last 24 hours
    gpu_reset_recent = []
    for gpi in gpu_reset_indices:
        timestamp = gpi[2]
        if timestamp is not None:
            time_difference = now - timestamp
            seconds_difference = time_difference.total_seconds()
            if seconds_difference <= 86400:
                gpu_reset_recent.append(gpi)

    # Logic for GPU reset:
    # 1. Xid error and no GPU reset or Xid error and GPU reset before more than 24 hours ago
    #       Recently rebooted: Tag and terminate
    #       Not recently rebooted: GPU reset
    # 2. Xid Error and GPU reset was done after the last Xid --> Healthy
    # 3. Xid Error and GPU reset before in the last 24 hours:
    #       If not rebooted even once in the last 12 hours: GPU reset
    #       Recently rebooted: Tag and Terminate
    #       Else: Reboot

    # If GPU reset was done
    if gpu_reset_present:
        last_xid = xid_indices[-1]
        last_probing = gpu_reset_indices[-1][0]
        # GPU reset was done after the last Xid --> Healthy
        if last_xid < last_probing:
            logger.info("Xid Error Check: Passed")
            return "", True
        elif gpu_reset_recent:
            # GPU reset before in the last 24 hours:
            #       If not rebooted even once in the last 12 hours: GPU reset
            #       Recently rebooted: Tag and Terminate
            #       Else: Reboot
            number_of_reboots,last_2hour_reboot,last_12hour_reboot = get_reboots_count()
            if last_12hour_reboot > 0 or number_of_reboots > 3:
                # Tag and Terminate
                logger.error("Xid Error Check: Failed")
                return "Terminate", False
            elif last_12hour_reboot == 0:
                # Reset GPU
                logger.error("Xid Error Check: Failed")
                return "GPU_Reset", False
            else:
                # Reboot
                logger.error("Xid Error Check: Failed")
                return "Reboot", False
        else:
            # GPU reset before more than 24 hours ago
            #       Recently rebooted: Tag and terminate
            #       Not recently rebooted: GPU reset
            return gpu_reset_logic()
    else:
        # No GPU reset was done
        #       Recently rebooted: Tag and terminate
        #       Not recently rebooted: GPU reset
        return gpu_reset_logic()

#Section 1: All Health Check functions.
########################################

# 1.1 Check the OCA Status
def read_oca_state(path, log_state=False):
    filename = os.path.basename(path)
    try:
        with open(path, 'r') as file:
            data = json.load(file)

        state = data.get("state", "UNKNOWN")
        if log_state:
            logger.info(f"{filename} state is: {state}")
        return state

    except FileNotFoundError:
        if log_state:
            logger.error(f"{filename} not found.")
        return "Not Started"
    except json.JSONDecodeError:
        if log_state:
            logger.error(f"Failed to parse {filename}.")
        return "Not Started"

def check_oca_status(log_state=False):
    rdma_configure_files = [
        "/var/run/oci-hpc/oci-hpc-rdma-configure.json",
        "/var/run/oci-hpc/oci-hpc-mlx-configure.json",
    ]
    rdma_configure_file = next(
        (path for path in rdma_configure_files if os.path.exists(path)),
        rdma_configure_files[0],
    )
    state_files = [
        rdma_configure_file,
        "/var/run/oci-hpc/oci-rdma-authentication.json",
    ]
    states = {
        os.path.basename(path): read_oca_state(path, log_state=log_state)
        for path in state_files
    }
    if all(state == "COMPLETED" for state in states.values()):
        return "COMPLETED"
    return ", ".join(f"{name}: {state}" for name, state in states.items() if state != "COMPLETED")

# 1.2 Check if the required Instance RDMA OCA plugins are enabled
def check_instance_rdma_plugins():
    instance_required_plugins = {
        "Compute HPC RDMA Authentication",
        "Compute HPC RDMA Auto-Configuration",
    }
    try:
        instance_plugins = get_instance_plugins()
    except (requests.RequestException, ValueError) as e:
        logger.error(f"RDMA Plugins Check: Failed to read OCA plugins config: {e}")
        return [f"Failed to read OCA plugins config: {e}"]

    instance_enabled_plugins = {
        instance_plugin.get("name")
        for instance_plugin in instance_plugins
        if isinstance(instance_plugin, dict) and instance_plugin.get("desiredState") == "ENABLED"
    }

    instance_plugin_issues = []
    for name in instance_required_plugins:
        if name not in instance_enabled_plugins:
            instance_plugin_issues.append(f"OCA plugin '{name}' is not ENABLED")

    if instance_plugin_issues:
        logger.warning("Instance RDMA Plugins Check: Failed")
    else:
        logger.info("Instance RDMA Plugins Check: Passed")

    return instance_plugin_issues

# 2.1 Check if the Oracle Cloud Agent is installed and up-to-date
def get_oca_version():
    # Run the shell command
    os_name = platform.system()

    if os_name == 'Linux':
        version = "Unknown"
        try:
            distro = platform.linux_distribution()[0]
        except:
            import distro
            distro = distro.name()

        if 'Ubuntu' in distro:
            command = ['snap', 'list', 'oracle-cloud-agent']
            try:
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logger.warning(f"Unable to get Oracle Cloud Agent version from snap: {e}")
                return version

            # Decode the output from bytes to string
            output = result.stdout.decode('utf-8')

            # Define the regular expression pattern for the version
            pattern = r'^oracle-cloud-agent\s+(\d+\.\d+\.\d+)'
            match = re.search(pattern, output, re.MULTILINE)
            if match:
                version = match.group(1)

        elif 'Oracle' in distro:
            result = subprocess.run(['rpm', '-qa'], stdout=subprocess.PIPE)

            # Decode the output from bytes to string
            output = result.stdout.decode('utf-8')

            # Define the regular expression pattern for the version
            pattern = r'oracle-cloud-agent-(\d+\.\d+\.\d+)'
            match = re.search(pattern, output)
            if match:
                version = match.group(1)

        if version < "1.39.0":
            logger.error(f"Oracle Cloud Agent: {version} needs to be updated to 1.39.0 or higher")
        else:
            logger.info(f"Oracle Cloud Agent: {version}")

        # Return the version
        return version

# 3.1 Check RTTCC status for supported GPU shapes and return status log.
def check_rttcc_status():
    devices = get_devices()
    if not devices:
        pass
        return []

    link_status = []
    status_dict = {"devices": {}}
    status = "disabled"

    for device in devices:
        command = [
            "sudo" if not is_user_root() else "",
            "mlxreg", "-d", device, "-y", "--get", "--reg_name=PPCC",
            "--indexes=local_port=1,pnat=0,lp_msb=0,algo_slot=0,algo_param_index=0"
        ]
        command = [c for c in command if c]  # Remove empty elements

        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output = result.stdout.decode('utf-8').split("\n")

            for line in output:
                if line.startswith("value"):
                    rttcc_value = line.split("|")[1].strip()
                    if rttcc_value == "0x00000001":
                        status_dict["devices"][device] = "enabled"
        except Exception as e:
            logger.error(f"Failed to check RTTCC on {device}: {e}")

    for device in status_dict["devices"]:
        if status_dict["devices"][device] == "enabled":
            logger.warning(f"RTTCC enabled on {device}")
            status = "enabled"
            link_status.append(f"RTTCC enabled on: {device}")
        else:
            logger.info(f"RTTCC status for {device}: disabled")
    if status == "disabled":
        logger.info("RTTCC Disabled Check: Passed")
    else:
        logger.error("RTTCC Disabled Check: Failed")

    return link_status

# 4.1 Check ECC errors for NVIDIA or AMD GPUs.
def check_ecc_errors():
    ecc_issues = []

    try:
        result = subprocess.run(['nvidia-smi', '-q'], stdout=subprocess.PIPE, timeout=SMI_TIMEOUT_SEC)
        if result.returncode == 0:
            output = result.stdout.decode('utf-8')
            sram_matches = re.findall(r'SRAM Uncorrectable\s+:\s+(\d+)', output)
            if len(sram_matches)==0:
                sram_matches = re.findall(r'SRAM Uncorrectable Parity\s+:\s+(\d+)', output)
            dram_matches = re.findall(r'DRAM Uncorrectable\s+:\s+(\d+)', output)
            gpu_matches = re.findall(r'\nGPU\s+(.*)\n', output)
            vol_sram_line = sram_matches[0::2]
            vol_dram_line = dram_matches[0::2]
            agg_sram_line = sram_matches[1::2]
            agg_dram_line = dram_matches[1::2]

            for i, gpu in enumerate(gpu_matches):
                logger.debug(f"GPU: {gpu}")
                if vol_sram_line[i] != "0":
                    logger.debug(f"Volatile SRAM Uncorrectable: {vol_sram_line[i]}")
                    ecc_issues.append(f"{gpu_matches[i]} - Volatile SRAM Uncorrectable: {vol_sram_line[i]}")
                if vol_dram_line[i] != "0":
                    logger.debug(f"Volatile DRAM Uncorrectable: {vol_dram_line[i]}")
                    ecc_issues.append(f"{gpu_matches[i]} - Volatile DRAM Uncorrectable: {vol_dram_line[i]}")
                if agg_sram_line[i] != "0":
                    logger.debug(f"Aggregate SRAM Uncorrectable: {agg_sram_line[i]}")
                    ecc_issues.append(f"{gpu_matches[i]} - Aggregate SRAM Uncorrectable: {agg_sram_line[i]}")
                if agg_dram_line[i] != "0":
                    logger.debug(f"Aggregate DRAM Uncorrectable: {agg_dram_line[i]}")
                    ecc_issues.append(f"{gpu_matches[i]} - Aggregate DRAM Uncorrectable: {agg_dram_line[i]}")

    except subprocess.TimeoutExpired:
        logger.warning(f"GPU ECC Test: Inconclusive - nvidia-smi timed out after {SMI_TIMEOUT_SEC}s")
        ecc_issues.append(f"nvidia-smi -q timed out after {SMI_TIMEOUT_SEC}s")

    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

        try:
            THRESHOLD = 5
            # Try detecting AMD GPU
            result = subprocess.run(["amd-smi", "metric", "--ecc", "--json"], capture_output=True, check=True, timeout=SMI_TIMEOUT_SEC)

            # Parse JSON output
            gpu_data = json.loads(result.stdout.decode('utf-8'))
            for gpu in gpu_data:
                if gpu["ecc"]["total_uncorrectable_count"] > THRESHOLD:
                    ecc_issues.append(f"GPU {gpu['gpu']} - ECC Errors: {gpu['ecc']['total_uncorrectable_count']}")

        except subprocess.TimeoutExpired:
            logger.warning(f"SRAM/DRAM ECC Test: Inconclusive - amd-smi timed out after {SMI_TIMEOUT_SEC}s")
            ecc_issues.append(f"amd-smi metric --ecc --json timed out after {SMI_TIMEOUT_SEC}s")

        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Skipping SRAM/DRAM ECC Test: nvidia-smi | amd-smi command not found.")
            return []

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding AMD JSON output: {e}")
            return []

    if not ecc_issues:
        logger.info("GPU ECC Test: Passed")
    else:
        logger.warning("GPU ECC Test: Failed")

    return ecc_issues

# 5.1 Check for row remap errors on GPUs.
def check_row_remap_errors():
    remap_issues = []
    recommended_action = None

    # Get instance metadata and shape
    shape = metadata.get('shape', '')

    # Skip the test for VM shapes
    if shape.startswith("VM."):
        pass
        return remap_issues, recommended_action

    # Proceed with the test for BM shapes
    try:
        # Run the nvidia-smi -q command
        result = subprocess.run(
            ['nvidia-smi', '--query-remapped-rows=remapped_rows.pending,remapped_rows.failure,remapped_rows.uncorrectable', '--format=csv,noheader'],
            stdout=subprocess.PIPE, timeout=SMI_TIMEOUT_SEC
        )

        if result.returncode != 0:
            logger.debug(f"Check row remap command exited with error code: {result.returncode}")

    except FileNotFoundError:
        logger.warning("Skipping Row Remap Test: nvidia-smi command not found")
        return remap_issues, recommended_action

    except subprocess.TimeoutExpired:
        logger.warning(f"Row Remap Test: Inconclusive - nvidia-smi timed out after {SMI_TIMEOUT_SEC}s")
        remap_issues.append(f"nvidia-smi --query-remapped-rows=remapped_rows.pending,remapped_rows.failure,remapped_rows.uncorrectable --format=csv,noheader timed out after {SMI_TIMEOUT_SEC}s")
        return remap_issues, recommended_action

    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')
    logger.debug("Output: {}".format(output))

    for i, line in enumerate(output.split('\n')):
        if line == "":
            continue
        tmp_data = line.split(",")
        tmp_data = [x.strip() for x in tmp_data]
        if tmp_data[0] != "0" and tmp_data[0] != "No":
            logger.debug(f"GPU: {i} - Row Remap Pending: {tmp_data[0]}")
            remap_issues.append(f"GPU: {i} Row Remap Pending: {tmp_data[0]}")
            recommended_action = "Reboot"
        if tmp_data[1] != "0" and tmp_data[1] != "No":
            logger.debug(f"GPU: {i} - Row Remap Failure: {tmp_data[1]}")
            recommended_action = "Terminate"
        if tmp_data[2] != "0" and tmp_data[2] != "No":
            logger.debug(f"GPU: {i} - Row Remap Uncorrectable: {tmp_data[2]}")
            if int(tmp_data[2]) > 512:
                remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable >512: {tmp_data[2]}")
                recommended_action = "Terminate"
            else:
                remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable <512: {tmp_data[2]}")
                recommended_action = "Reboot"

    if len(remap_issues) == 0:
        logger.info("GPU Row Remap Test: Passed")
    else:
        logger.warning("GPU Row Remap Test: Failed")

    return remap_issues, recommended_action

# 6.1 Check the number of GPUs available on the system.
def check_gpu_count():

    lspci_expected_results_gpu = [
        '0f:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
        '2d:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
        '44:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
        '5b:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
        '89:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
        'a8:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
        'c0:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
        'd8:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)'
    ]
    lspci_expected_results_l40s = [
        '16:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)',
        '38:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)',
        '82:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)',
        'ac:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)'
    ]
    lspci_expected_results_a10 = [
        '17:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)',
        '31:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)',
        'b1:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)',
        'ca:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)'
    ]

    lspci_expected_results_gb200 = [
        '0008:01:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0009:01:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0018:01:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0019:01:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)'
    ]

    lspci_expected_results_gb200_v3 = [
        '0008:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0009:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0018:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0019:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)'
    ]

    lspci_expected_results_gb300 = [
        '0008:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0009:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0018:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)',
        '0019:06:00.0 3D controller: NVIDIA Corporation Device 2941 (rev a1)'
    ]

    lspci_expected_results_b300 = [
        "14:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)",
        "32:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)",
        "49:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)",
        "60:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)",
        "8e:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)",
        "ad:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)",
        "c5:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)",
        "dd:00.0 3D controller: NVIDIA Corporation Device 3182 (rev a1)"
    ]

    shape = metadata.get('shape')
    tmp_results = []

    # Check the number of GPUs for AMD
    if "BM.GPU.MI" in shape:
        try:
            result = subprocess.run(['amd-smi', 'list'], stdout=subprocess.PIPE, timeout=SMI_TIMEOUT_SEC)
            output = result.stdout.decode('utf-8')
            gpu_count = output.count("GPU")  # Count occurrences of "GPU"
            tmp_results = []
            expected_no_gpu = 8

            if gpu_count == expected_no_gpu:
                logger.info("GPU Count Test: Passed")
            else:
                logger.warning("GPU Count Test: Failed")
                tmp_results.append(f"Expected {expected_no_gpu} GPUs, found {gpu_count} using amd-smi command")

        except subprocess.TimeoutExpired:
            logger.warning("GPU Count Test: Failed - amd-smi list timed out")
            tmp_results.append(f"amd-smi list timed out after {SMI_TIMEOUT_SEC}s")

        except FileNotFoundError:
            logger.warning("Skipping GPU count test: amd-smi command not found")

        return tmp_results

    # Check the number of GPUs for NVIDIA
    try:
        result = subprocess.run(['nvidia-smi', '--list-gpus'], stdout=subprocess.PIPE, timeout=SMI_TIMEOUT_SEC)
        output = result.stdout.decode('utf-8').strip()

        # Handle "No devices found" case
        if "No devices found" in output:
            logger.error("GPU Count Test: Failed - No devices found using nvidia-smi")
            return ["No GPUs detected"]

        if "Unable to determine the device handle" in output:
            logger.error("GPU Count Test: Failed - Unable to determine the device handle for one or more devices")
            return ["GPU device handle problem"]

        lines = output.split('\n')
        # Remove empty lines
        lines = [line for line in lines if line]
        if "GPU.GB" in shape or shape in ["BM.GPU.L40S-NC.4", "BM.GPU.A10.4"]:
            expected_gpus = 4
        elif shape in ["VM.GPU.A10.1", "VM.GPU.A100.40G.1", "VM.GPU.A100.80G.1"]:
            expected_gpus = 1
        elif shape == "VM.GPU.A10.2":
            expected_gpus = 2
        else:
            expected_gpus = 8

        if len(lines) == expected_gpus:
            logger.info("GPU Count Test: Passed")
        else:
            logger.error("GPU Count Test: Failed")
            tmp_results.append(f"Expected {expected_gpus} GPUs, found {len(lines)} using nvidia-smi command")

        return tmp_results

    except FileNotFoundError:
        try:
            # Check if lspci is available
            result = subprocess.run(['lspci', '-v'], stdout=subprocess.PIPE)
            output = result.stdout.decode('utf-8')

            # Check if the expected results are in the output
            lines = output.split('\n')
            tmp_results = []
            missing_gpus = []
            shape = metadata.get('shape')
            find_number = ""
            expected_gpus = ""
            lspci_expected_results = ""

            if shape == "BM.GPU.L40S-NC.4":
                find_number = "26b9"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_l40s
            elif shape in ["BM.GPU.A10.4", "VM.GPU.A10.1", "VM.GPU.A10.2"]:
                find_number = "GA102GL"
                if shape == "VM.GPU.A10.1":
                    expected_gpus = 1
                elif shape == "VM.GPU.A10.2":
                    expected_gpus = 2
                else:
                    expected_gpus = 4
                lspci_expected_results = lspci_expected_results_a10
            elif shape in ["BM.GPU.A100-v2.8", "VM.GPU.A100.40G.1", "VM.GPU.A100.80G.1", "BM.GPU.H100.8", "BM.GPU.H200.8", "BM.GPU.B200.8", "BM.GPU.B4.8", "BM.GPU4.8"]:
                find_number = "2330"
                if shape in ["VM.GPU.A100.40G.1", "VM.GPU.A100.80G.1"]:
                    expected_gpus = 1
                else:
                    expected_gpus = 8
                lspci_expected_results = lspci_expected_results_gpu
            elif shape in ["BM.GPU.GB200-v3.4"]:
                find_number = "2941"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_gb200_v3
            elif shape in ["BM.GPU.GB300.4"]:
                find_number = "2941"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_gb300
            elif shape in ["BM.GPU.GB300.4"]:
                find_number = "3182"
                expected_gpus = 8
                lspci_expected_results = lspci_expected_results_b300
            elif "GPU.GB" in shape:
                find_number = "2941"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_gb200
            for line in lines:
                if line.find("NVIDIA") != -1 and line.find(find_number) != -1:
                    tmp_results.append(line)
            if not len(tmp_results) == expected_gpus:
                logger.debug(f"Expected {expected_gpus} GPUs, found {len(tmp_results)} in lspci output")
                for line in lspci_expected_results:
                    if line not in tmp_results:
                        missing_gpus.append(f"Missing GPU: {line}")
            if len(tmp_results) == expected_gpus:
                logger.info("GPU Count Test: Passed")
            else:
                logger.warning("GPU Count Test: Failed")
            return missing_gpus

        except FileNotFoundError:
            logger.warning("Skipping GPU count test: nvidia-smi and lspci commands not found")
            return None

        except subprocess.TimeoutExpired:
            logger.error(f"GPU Count Test: Failed - nvidia-smi timed out after {SMI_TIMEOUT_SEC}s")
            return [f"nvidia-smi --list-gpus timed out after {SMI_TIMEOUT_SEC}s"]

# 7.1 Checks PCIe link width for NVIDIA or AMD based on instance shape.
def check_gpu_pcie():
    shape = metadata.get('shape', '')

    expected_pcie_width = 16  # Expected PCIe width

    if "BM.GPU.MI" in shape:
        try:
            result = subprocess.run(['amd-smi', 'metric', '--pcie'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=SMI_TIMEOUT_SEC)
            output = result.stdout.decode('utf-8').strip()

            if result.returncode != 0 or "No devices were found" in output:
                logger.error("GPU PCIe Width Test: Failed - No devices were found")
                return ["No GPUs detected"]

            # Extract PCIe WIDTH values correctly
            pcie_widths = re.findall(r'^\s*WIDTH:\s*(\d+)', output, re.MULTILINE)
            pcie_widths = list(map(int, pcie_widths)) if pcie_widths else []

            if all(width == expected_pcie_width for width in pcie_widths):
                logger.info("GPU PCIe Width Test: Passed")
            else:
                logger.error("GPU PCIe Width Test: Failed")
                return [f"Expected PCIe width {expected_pcie_width}, but found {pcie_widths}"]

        except subprocess.TimeoutExpired:
            logger.error(f"GPU PCIe Width Test: Failed - amd-smi timed out after {SMI_TIMEOUT_SEC}s")
            return [f"amd-smi metric --pcie timed out after {SMI_TIMEOUT_SEC}s"]

        except FileNotFoundError:
            logger.warning("GPU PCIe Width Test: Skipping - amd-smi command not found")
            return ["AMD PCIe Width Test Skipped"]

    else:
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=pcie.link.width.current', '--format=csv,noheader'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=SMI_TIMEOUT_SEC
            )
            output = result.stdout.decode('utf-8').strip()

            if "No devices were found" in output:
                logger.error("GPU PCIe Width Test: Failed - No devices were found")
                return ["No GPUs detected"]

            widths = list(map(int, output.split("\n")))
            if all(width == expected_pcie_width for width in widths):
                logger.info("GPU PCIe Width Test: Passed")
            else:
                logger.error("GPU PCIe Width Test: Failed")
                return [f"Expected PCIe width {expected_pcie_width}, but found {widths}"]

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode().strip() if e.stderr else "Unknown error"
            logger.error(f"GPU PCIe Width Test: Failed with error: {error_msg}")
            return ["NVIDIA PCIe Width Test Failed"]

        except FileNotFoundError:
            logger.warning("GPU PCIe Width Test: Skipping - `nvidia-smi` command not found")
            return ["NVIDIA PCIe Width Test Skipped"]

        except subprocess.TimeoutExpired:
            logger.error(f"GPU PCIe Width Test: Failed - nvidia-smi timed out after {SMI_TIMEOUT_SEC}s")
            return [f"nvidia-smi PCIe query timed out after {SMI_TIMEOUT_SEC}s"]

    return []

# 8.1 GPU Bandwidth test using the BandwidthTest class

# 9.1 Check to see if any devices have fallen of the bus
def check_bus():
    command = ['lspci', '-v']
    result = subprocess.run(command, stdout=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    lines = output.split('\n')
    bus_issues = []
    for line in lines:
        if line.find('(rev ff)') != -1:
            bus_issues.append(line)
    if len(bus_issues) > 0:
        logger.error("Devices have fallen off the bus")
    if len(bus_issues) == 0:
        logger.info("Bus Check Test: Passed")
        return(bus_issues)
    else:
        logger.warning("Bus Check Test: Failed")
        return(bus_issues)

# 10.1 Check RDMA link status for Mellanox devices.
def get_mlxlink_field(output, field_name):
    match = re.search(rf'^\s*{re.escape(field_name)}\s*:\s*(.*?)\s*$', output, re.MULTILINE)
    if not match:
        return ""
    color_pattern = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return re.sub(color_pattern, '', match.group(1)).strip()


def parse_mlxlink_float_values(value):
    values = []
    for item in value.split(","):
        item = item.strip()
        if not item or item.upper() in ("N/A", "NA"):
            continue
        try:
            values.append(float(item))
        except ValueError:
            continue
    return max(values) if values else None


def check_rdma_link_status():
    status = True

    link_issues = []
    devices = get_mlxlink_devices()

    for device in devices:
        # Run the mlxlink command
        if not is_user_root():
            command = ['sudo', 'mlxlink', '-d', device, '-m', '-c', '-e']
        else:
            command = ['mlxlink', '-d', device, '-m', '-c', '-e']
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Decode the output from bytes to string
        output = result.stdout.decode('utf-8')
        stderr = result.stderr.decode('utf-8')

        if stderr and stderr.find("-E-") != -1:
            stderr = stderr.split("\n")
            stderr_line = ", ".join(stderr)
            logger.debug(f"{device}: {stderr_line}")
            link_issues.append(f"{device}: {stderr[0]}")
            status = "False"
            continue

        # Find the line containing "Recommendation"
        color_pattern = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        link_state = re.search(r'\nState.*', output).group().split(":")[1].strip()
        recommendation = re.search(r'Recommendation.*', output).group().split(":")[1].strip()
        vendor_serial_num = re.search(r'Vendor Serial Number.*', output).group().split(":")[1].strip()
        nic_fw_version = re.search(r'Firmware Version.*', output).group().split(":")[1].strip()
        cable_fw_version = re.search(r'FW Version.*', output).group().split(":")[1].strip()
        physical_BER = get_mlxlink_field(output, "Raw Physical BER")
        if not physical_BER:
            physical_BER = get_mlxlink_field(output, "Raw Physical BER Per Lane")
        physical_BER_value = parse_mlxlink_float_values(physical_BER)
        # Remove hidden characters from the output
        link_state = re.sub(color_pattern, '', link_state)
        nic_fw_version = re.sub(color_pattern, '', nic_fw_version)
        recommendation = re.sub(color_pattern, '', recommendation)

        logger.debug(f"{device}: {vendor_serial_num} - {cable_fw_version} - {nic_fw_version} - {link_state} - {recommendation}")

        # Extract the part after the ":" and print it along with the device name
        if link_state != "Active":
            logger.debug(f"{device}: {link_state}")
            link_issues.append(f"{device} - {vendor_serial_num} - {cable_fw_version} - {nic_fw_version}: {link_state}")
            status = False
        if "No issue was observed" not in recommendation:
            logger.debug(f"{device}: {recommendation}")
            if "Bad signal integrity" in recommendation and physical_BER_value is None:
                logger.debug(f"Recommandation is {recommendation} but Raw Physical BER could not be parsed: {physical_BER}")
                link_issues.append(f"{device} - {vendor_serial_num} - {cable_fw_version} - {nic_fw_version}: {recommendation}")
                status = False
            elif "Bad signal integrity" in recommendation and physical_BER_value < 1e-07:
                logger.debug(f"Recommandation is {recommendation} but the Physical error are low enough that it can be ignored")
                status=True
            elif "Bad signal integrity" in recommendation and physical_BER_value >= 1e-07:
                logger.debug(f"Recommandation is {recommendation} and the Physical error count is too high to be ignored: {physical_BER}")
                link_issues.append(f"{device} - {vendor_serial_num} - {cable_fw_version} - {nic_fw_version}: {recommendation}")
                status = False
            else :
                logger.debug(f"Recommandation is {recommendation}")
                link_issues.append(f"{device} - {vendor_serial_num} - {cable_fw_version} - {nic_fw_version}: {recommendation}")
                status = False
        else:
            logger.debug(f"{device}: {recommendation}")

    if status:
        logger.info("RDMA Link Status Check: Passed")
    else:
        logger.warning("RDMA Link Status Check: Failed")
    return link_issues

# 11.1 RDMA link flapping test using the LinkFlappingTest class

# 12.1 Xid error check using the XidChecker class

# 13.1 Determine the shape and required authenticated count for WPA authentication check.
def check_wpa_auth(metadata):
    shape = metadata.get('shape')

    # Skip the test for VM shapes
    if shape.startswith("VM."):
        pass
        return []

    interface_names = []
    if is_multiplanar(shape):
        interface_names = discover_multiplanar_wpa_interfaces(shape)
        required_authenticated = len(interface_names)
    elif shape in ["BM.GPU.H100.8", "BM.GPU.B4.8", "BM.GPU.A100-v2.8", "BM.GPU4.8","BM.GPU.B4.8"]:
        interface_range = range(16)
        required_authenticated = 16
        interface_names = ["rdma" + str(i) for i in interface_range]
    elif shape in ["BM.GPU.H200.8", "BM.GPU.B200.8", "BM.GPU.B300.8", "BM.GPU.B300.HS.8", "BM.GPU.MI300X.8", "BM.GPU.MI355X-v1.8", "BM.GPU.RTXPRO.8"]:
        interface_range = range(8)
        required_authenticated = 8
        interface_names = ["rdma" + str(i) for i in interface_range]
    elif shape in ["BM.GPU.GB200-v3.4"]:
        interface_range = range(8)
        required_authenticated = 8
        interface_names = ["rdma" + str(i) for i in interface_range]
    elif shape in ["BM.GPU.GB300.4"]:
        interface_range = range(8)
        required_authenticated = 8
        interface_names = ["rdma" + str(i) for i in interface_range]
    elif "GPU.GB" in shape:
        interface_range = range(4)
        required_authenticated = 0
        interface_names = ["rdma" + str(i) for i in interface_range]
    else:
        logger.error("Unsupported machine shape.")
        return ["Unsupported machine shape."]

    authenticated_count = 0
    wpa_auth_issues = []
    current_state = "None"  # Define initial state, can be updated based on actual logic
    auth_status = {key: 0 for key in interface_names}
    warning = {key: [] for key in interface_names}
    action = None
    for i in range(5):
        # Check each RDMA interface for WPA authentication status
        for interface in interface_names:
            try:
                if not is_user_root():
                    command = ['sudo', 'wpa_cli', 'status', '-i', interface]
                else:
                    command = ['wpa_cli', 'status', '-i', interface]

                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.stderr.decode('utf-8') != '':
                    warning[interface] = result.stderr.decode('utf-8').rstrip("\n")
                for line in result.stdout.decode('utf-8').splitlines():
                    if "Supplicant PAE state" in line:
                        if "AUTHENTICATED" in line:
                            auth_status[interface] = 1
                        break
            except subprocess.CalledProcessError as e:
                wpa_auth_issues.append(f"Error checking {interface}: {e}")
                logger.warning(f"Error checking {interface}: {e}")
        authenticated_count = sum(auth_status.values())
        if authenticated_count >= required_authenticated:
            break
        else:
            time.sleep(5)

    # Determine action based on authentication result
    if authenticated_count < required_authenticated:
        wpa_auth_issues.append(f"Only {authenticated_count} interfaces are AUTHENTICATED; expected at least {required_authenticated}.")
        for i in warning.keys():
            if auth_status[i] == 0:
                logger.warning(warning[i])
        logger.error("WPA Authentication Check: Failed")
    else:
        logger.info("WPA Authentication Check: Passed")

    return wpa_auth_issues if wpa_auth_issues else []

# 14.1 Check the status of the Fabric Manager
def check_fabric_manager():
    fabric_manager_health = False
    try:
        # Run the nvidia-smi -q -i 0 | grep -i -A 2 Fabric
        result = subprocess.run('nvidia-smi -q -i 0 | grep -i -A 2 Fabric', shell=True, stdout=subprocess.PIPE, timeout=SMI_TIMEOUT_SEC)
        if result.returncode != 0:
            logger.debug(f"Fabric Manager Check exited with error code: {result.returncode}")

    except FileNotFoundError:
        logger.warning("Skipping Fabric Manager test: nvidia-smi command not found")
        return fabric_manager_health

    except subprocess.TimeoutExpired:
        logger.warning(f"Fabric Manager Check: Failed - nvidia-smi timed out after {SMI_TIMEOUT_SEC}s")
        return False

    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')
    logger.debug("Output: {}".format(output))
    fabric_manager_status=False
    fabric_manager_state=False
    for i, line in enumerate(output.split('\n')):
        if "State" in line:
            if "Completed" in line:
                fabric_manager_state = True
        elif "Status" in line:
            if "Success" in line:
                fabric_manager_status = True
        else:
            continue
    fabric_manager_health= ( fabric_manager_status and fabric_manager_state )
    return fabric_manager_health

# 15.1 Retrieve online CPUs and check if their profile is set to 'performance'.
def get_current_cpu_profile():
    try:
        # Get instance metadata
        shape = metadata.get('shape', '')

        # Skip VM shapes
        if shape.startswith("VM."):
            pass
            return []

        # Get online CPUs from lscpu
        output = subprocess.check_output(["lscpu"], universal_newlines=True)
        online_cpu_list = None

        for line in output.splitlines():
            if "On-line CPU(s) list:" in line:
                online_cpu_list = line.split(":")[1].strip()
                break

        if not online_cpu_list:
            logger.error("Could not determine online CPUs. Check `lscpu` output.")
            return []

        # Convert CPU range to a list of integers
        online_cpus = []
        for part in online_cpu_list.split(","):
            if "-" in part:
                start, end = map(int, part.split("-"))
                online_cpus.extend(range(start, end + 1))
            else:
                online_cpus.append(int(part))

    except Exception as e:
        logger.error(f"Failed to get online CPUs: {e}")
        return []

    # Check CPU governor for only online CPUs
    cpu_profile_issues = []

    for cpu_id in online_cpus:
        cpu_file = f"/sys/devices/system/cpu/cpu{cpu_id}/cpufreq/scaling_governor"
        for attempt in range(3):  # Retry up to 3 times
            try:
                with open(cpu_file, 'r') as f:
                    result = f.read().strip()

                if result == "performance":
                    continue
                else:
                    logger.warning(f"CPU {cpu_id}: Profile is '{result}', expected 'performance'.")
                    cpu_profile_issues.append(f"CPU {cpu_id}: {result}")

                break  # Exit retry loop on success

            except Exception as e:
                if "Device or resource busy" in str(e):
                    if attempt < 2:
                        time.sleep(0.5)  # Wait before retrying
                    else:
                        logger.warning(f"CPU {cpu_id}: Scaling governor file is busy. Skipping after 3 attempts.")
                else:
                    logger.error(f"Skipping CPU {cpu_id}: {e}")
                    break  # Skip CPU if persistently busy

    if not cpu_profile_issues:
        logger.info("CPU Profile Check: Passed")  # All CPUs are set to 'performance'.
    else:
        logger.error("Some CPUs failed the profile check.")

    return cpu_profile_issues

# 16.1 Check for pending bad pages on GPUs, for AMD only.
def check_bad_pages():
    try:
        result = subprocess.run(["amd-smi", "bad-pages", "--json"], capture_output=True, check=True, timeout=SMI_TIMEOUT_SEC)
        data = json.loads(result.stdout.decode('utf-8'))
    except subprocess.TimeoutExpired:
        return [f"amd-smi bad-pages --json timed out after {SMI_TIMEOUT_SEC}s"]
    except FileNotFoundError:
        logger.warning("GPU Pending Bad Pages Check: Skipping - amd-smi command not found")
        return ["AMD bad-pages check skipped (amd-smi not found)"]
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        logger.error(f"Error executing amd-smi or parsing JSON: {e}")
        return [f"amd-smi bad-pages failed or returned invalid JSON: {e}"]

    errors = []

    for gpu in data:
        if gpu.get("pending") != "No bad pages found.":
            errors.append(f"Error: GPU {gpu['gpu']} has bad pages pending: {gpu['pending']}")

    if errors:
        for error in errors:
            logger.error(error)
    else:
        logger.info("GPU Pending Bad Pages Check: Passed")

# 17.1 Check if required RDMA interfaces have valid IP addresses
def check_ip_addresses():
    devices = get_rdma_devices()
    devices_per_interface={}
    infiniband_dir="/sys/class/infiniband"
    current_shape = metadata.get('shape', '') if 'metadata' in globals() else get_metadata().get('shape', '')
    multiplanar = is_multiplanar(current_shape)
    for device in devices:
        device_name = os.path.basename(device)
        device_path = os.path.join(infiniband_dir, device_name, "device", "net")
        if os.path.exists(device_path):
            interfaces = os.listdir(device_path)
            for interface in interfaces:
                devices_per_interface[interface]=device_name
                break

    missing_ips=[]
    multiple_ips=[]
    for device in devices:
        device_name = os.path.basename(device)
        if device_name not in devices_per_interface.values():
            missing_ips.append(f"{device_name} (no network interface found)")

    interface_map = {}
    checked_interfaces = set()
    for interface, addrs in psutil.net_if_addrs().items():
        if interface not in devices_per_interface.keys():
            continue
        checked_interfaces.add(interface)
        ip_addresses = []
        # Get IPv4, or IPv6 on B300, addresses
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ip_addresses.append(addr.address)
            elif (
                addr.family == socket.AF_INET6
                and (current_shape in ("BM.GPU.B300.8", "BM.GPU.B300.HS.8") or multiplanar)
                and not is_link_local_ipv6_address(addr.address)
            ):
                ip_addresses.append(addr.address)
        if len(ip_addresses) == 0:
            missing_ips.append(interface)
        elif len(ip_addresses) > 1:
            multiple_ips.append(f"{interface} ({','.join(ip_addresses)})")
        # Store details
        interface_map[interface] = {
            "device_name": devices_per_interface[interface],
            "interface": interface,
            "ip_address": ip_addresses[0] if ip_addresses else None,
            "ip_addresses": ip_addresses
        }
    for interface in devices_per_interface:
        if interface not in checked_interfaces:
            missing_ips.append(interface)
    return missing_ips,multiple_ips,interface_map

# 18.1 Check NVLinks speeds
def get_nvlink_speed():
    gpu_nvlink_info = {
        "BM.GPU4.8":         {"count": 12, "speed": 25,      "gpu": 8},
        "BM.GPU.B4.8":       {"count": 12, "speed": 25,      "gpu": 8},
        "BM.GPU.A100-v2.8":  {"count": 12, "speed": 25,      "gpu": 8},
        "BM.GPU.H100.8":     {"count": 18, "speed": 25,      "gpu": 8},
        "BM.GPU.H200.8":     {"count": 18, "speed": 25,      "gpu": 8},
        "BM.GPU.B200.8":     {"count": 18, "speed": 50,      "gpu": 8},
        "BM.GPU.B300.8":     {"count": 18, "speed": 50,      "gpu": 8},
        "BM.GPU.B300.HS.8":  {"count": 18, "speed": 50,      "gpu": 8},
        "BM.GPU.GB200.4":    {"count": 18, "speed": 50,      "gpu": 4},
        "BM.GPU.GB200-v2.4": {"count": 18, "speed": 50,      "gpu": 4},
        "BM.GPU.GB200-v3.4": {"count": 18, "speed": 50,      "gpu": 4},
        "BM.GPU.GB300.4":    {"count": 18, "speed": 50,      "gpu": 4},
        "VM.GPU.A100.40G.1": {"count": 12, "speed": 25,      "gpu": 1},
        "VM.GPU.A100.80G.1": {"count": 12, "speed": 25,      "gpu": 1}
    }

    shape = metadata.get('shape')
    try:
        info = gpu_nvlink_info[shape]
    except KeyError:
        logger.info(f"Skipping NVLink speed check: unsupported GPU shape {shape}")
        return []
    count_expected = info['count']
    speed_expected = info['speed']
    expected_gpu = info['gpu']

    error = False
    checked = 0
    for gpu_index in range(expected_gpu):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=mig.mode.current", "--format=csv,noheader", "-i", str(gpu_index)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=SMI_TIMEOUT_SEC,
                check=True
            )
            mig_output = result.stdout.decode()

            if "enabled" in mig_output.lower():
                logger.info(f"Skipping NVLINK check on MIG enabled GPU: {gpu_index}")
                continue

        except subprocess.TimeoutExpired:
            logger.warning(f"GPU {gpu_index}: MIG status check command timed out after {SMI_TIMEOUT_SEC}s.")
        except subprocess.CalledProcessError as e:
            logger.warning(f"GPU {gpu_index}: MIG status check command failed with return code {e.returncode}.")
        except Exception as e:
            logger.warning(f"GPU {gpu_index}: MIG status check unexpected error: {e}")

        try:
            result = subprocess.run(
                ["nvidia-smi", "nvlink", "-s", "-i", str(gpu_index)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=SMI_TIMEOUT_SEC,
                check=True
            )
            gpu_output = result.stdout.decode()

            link_speeds = re.findall(r'Link \d+: ([\d.]+) GB/s', gpu_output)
            speeds_float = [float(s) for s in link_speeds]

            count = len(speeds_float)
            speeds_match = all(speed >= speed_expected for speed in speeds_float)

            if count != count_expected:
                logger.error(f"GPU {gpu_index}: ERROR: NVLink count mismatch!")
                error = True
            if not speeds_match:
                logger.error(f"GPU {gpu_index}: ERROR: One or more link speeds do not match expected ({speed_expected} GB/s)")
                error = True
        except subprocess.TimeoutExpired:
            logger.warning(f"GPU {gpu_index}: NVLink speed check command timed out after {SMI_TIMEOUT_SEC}s.")
        except subprocess.CalledProcessError as e:
            logger.warning(f"GPU {gpu_index}: NVLink speed check command failed with return code {e.returncode}.")
        except Exception as e:
            logger.warning(f"GPU {gpu_index}: NVLink speed check unexpected error: {e}")
        checked += 1
    if error:
        return False
    else:
        if checked:
            logger.info(f"For {checked} GPUs, {count_expected} links detected as expected and all speeds as expected {speed_expected} GB/s : Passed")
        return True

# 19.1 Run dcgmi health check
def run_dcgmi_health():
    IMEX_TOKENS = ("imex domain status is down", "imex")

    warning_messages = []
    error_messages = []

    def is_imex_related(text):
        t = (text or "").lower()
        return any(tok in t for tok in IMEX_TOKENS)

    def collect_leaf_status_details(node, target_status, path=()):
        # Collect detail groups from LEAF nodes whose `value` == target_status.
        # - Ignores aggregate markers that have matching descendants.
        # - Ignores top-level "Overall Health" marker.
        groups = []

        if isinstance(node, dict):
            nested_groups = []
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    nested_groups.extend(
                        collect_leaf_status_details(v, target_status, path + (str(k),))
                    )

            value = str(node.get("value", "")).strip().lower()
            is_target = value == target_status
            is_overall_marker = len(path) > 0 and path[-1] == "Overall Health"

            if is_target and not is_overall_marker:
                if nested_groups:
                    # This is a summary node; keep only detailed child nodes
                    groups.extend(nested_groups)
                else:
                    # Leaf node: prefer overflow details
                    details = []
                    overflow = node.get("overflow")
                    if isinstance(overflow, list):
                        details.extend(str(x).strip() for x in overflow if str(x).strip())

                    # Fallback to other string fields
                    if not details:
                        for k, v in node.items():
                            if k in ("value", "children"):
                                continue
                            if isinstance(v, str):
                                s = v.strip()
                                if s and s.lower() != target_status:
                                    details.append(s)

                    if details:
                        groups.append(details)

                return groups

            groups.extend(nested_groups)

        elif isinstance(node, list):
            for i, item in enumerate(node):
                groups.extend(collect_leaf_status_details(item, target_status, path + (str(i),)))

        return groups

    # 1) Check dcgmi availability
    try:
        subprocess.check_output(['dcgmi', '--version'], universal_newlines=True, timeout=10)
    except FileNotFoundError:
        warning_messages.append("dcgmi is not installed or not in PATH.")
        return True, warning_messages, error_messages

    # 2) Ensure health watches are configured
    try:
        health_output = subprocess.check_output(
            ['dcgmi', 'health', '-c'],
            universal_newlines=True,
            stderr=subprocess.STDOUT,
            timeout=10
        )
        need_setup = "Error: Health watches not enabled. Please enable watches." in health_output
    except subprocess.CalledProcessError as e:
        health_output = e.output
        need_setup = "Error: Health watches not enabled. Please enable watches." in health_output

    if need_setup:
        try:
            setup_output = subprocess.check_output(
                ['dcgmi', 'health', '-s', 'a'],
                universal_newlines=True,
                stderr=subprocess.STDOUT,
                timeout=30
            )
            if "Health monitor systems set successfully." not in setup_output:
                warning_messages.append("Unexpected dcgmi health setup output")
                return True, warning_messages, error_messages
            time.sleep(5)
        except subprocess.CalledProcessError as e:
            warning_messages.append("Could not set up dcgmi health")
            detail = (e.output or "").strip()
            if detail and not is_imex_related(detail):
                warning_messages.append(detail)
            return True, warning_messages, error_messages

    # 3) Evaluate final health
    try:
        health_json = subprocess.check_output(
            ['dcgmi', 'health', '-c', '-j'],
            universal_newlines=True,
            stderr=subprocess.STDOUT,
            timeout=10
        )
        payload = json.loads(health_json)

        overall = str(payload.get("body", {}).get("Overall Health", {}).get("value", "")).strip()
        status = overall.lower()

        if status == "healthy":
            return True, warning_messages, error_messages

        if status == "warning":
            warning_messages.append("Overall dcgmi Health is 'Warning'")

            warning_groups = collect_leaf_status_details(
                payload.get("body", {}), "warning", path=("body",)
            )
            seen = set()
            for group in warning_groups:
                for line in group:
                    line = (line or "").strip()
                    if line and line not in seen:
                        warning_messages.append(line)
                        seen.add(line)

            return True, warning_messages, error_messages

        if status == "failure":
            failure_groups = collect_leaf_status_details(
                payload.get("body", {}), "failure", path=("body",)
            )

            # If failure marker exists but no actionable details, treat as warning
            if not failure_groups:
                warning_messages.append(
                    "dcgmi reported a failure status, but no specific non-IMEX issue details were found; treating this as a warning"
                )
                return True, warning_messages, error_messages

            # Strict IMEX rule: ignore only if ALL failure groups are IMEX-related
            non_imex_groups = []
            for group in failure_groups:
                if not is_imex_related(" | ".join(group)):
                    non_imex_groups.append(group)

            if not non_imex_groups:
                return True, warning_messages, error_messages

            # Real non-IMEX failures
            error_messages.append("Overall dcgmi Health is 'Failure' with non-IMEX reason(s)")
            seen = set()
            for group in non_imex_groups:
                for line in group:
                    line = (line or "").strip()
                    if line and line not in seen and not is_imex_related(line):
                        error_messages.append(line)
                        seen.add(line)

            return False, warning_messages, error_messages

        error_messages.append(f"Unexpected dcgmi Overall Health value: '{overall}'")
        return False, warning_messages, error_messages

    except subprocess.TimeoutExpired:
        warning_messages.append("dcgmi health check timed out")
        return True, warning_messages, error_messages
    except subprocess.CalledProcessError as e:
        warning_messages.append("Error running dcgmi health check")
        detail = (e.output or "").strip()
        if detail and not is_imex_related(detail):
            warning_messages.append(detail)
        return True, warning_messages, error_messages
    except json.JSONDecodeError as e:
        warning_messages.append(f"Error parsing dcgmi health JSON output: {e}")
        return True, warning_messages, error_messages

# 20.1 Run rocminfo check
def run_rocminfo_check():
    try:
        # Run 'rocminfo' and capture stdout as text
        result = subprocess.run(["rocminfo"], capture_output=True, text=True, check=True, timeout=10)
        output_lines = result.stdout.strip().splitlines()

        # Check if the output has more than 100 lines
        if len(output_lines) < 101:
            logger.error("rocminfo output length is not as expected")
            return False
        # Check if the last line is *** Done ***
        if output_lines[-1] != '*** Done ***':
            logger.error("Last line is not '*** Done ***'. rocminfo output is not as expected")
            return False
        # Check for presence of "HSA Agents" (case-sensitive)
        if any("HSA Agents" in line for line in output_lines):
            return True
        else:
            logger.error("'HSA Agents' not found in rocminfo output. rocminfo output is not as expected")
            return False
    except FileNotFoundError:
        logger.error("rocminfo is not installed or not in PATH")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"rocminfo execution failed: {e}")
        return False
    except Exception as e:
        logger.error(f"rocminfo health check unexpected error: {str(e)}")
        return False

# 21.1 Run LBNL NHC
def run_nhc_check():
    nhc_config_file = "/etc/nhc/oci.nhc.conf"
    nhc_binary = "/usr/sbin/nhc"
    nhc_log_file = "/var/log/nhc.log"
    nhc_timeout_sec = 60
    warning_messages = []
    error_messages = []

    if not Path(nhc_config_file).is_file():
        message = f"Cannot run LBNL node health checks. Missing NHC config: {nhc_config_file}"
        return True, [message], []

    if not Path(nhc_binary).is_file():
        message = f"Cannot run LBNL node health checks. Missing NHC binary: {nhc_binary}"
        return True, [message], []

    try:
        subprocess.run(["nvme", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=5)
    except subprocess.TimeoutExpired:
        message = "Cannot run LBNL node health checks. LBNL node health checks timed out after 5s while checking nvme-cli availability."
        return True, [message], []
    except (subprocess.CalledProcessError, FileNotFoundError):
        message = "Cannot run LBNL node health checks. nvme-cli not installed."
        return True, [message], []

    if os.path.isfile(nhc_log_file):
        try:
            os.remove(nhc_log_file)
        except PermissionError:
            message = "Cannot run LBNL node health checks. Try running as root or with elevated privileges."
            return True, [message], []
        except Exception as e:
            message = f"Cannot run LBNL node health checks. Error deleting {nhc_log_file}: {e}"
            return True, [message], []

    cmd = [
        'sudo',
        nhc_binary,
        '-c', nhc_config_file,
        '-a',
        '-v'
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False, # Don't raise exception on nonzero exit
            timeout=nhc_timeout_sec
        )
    except subprocess.TimeoutExpired:
        message = f"LBNL node health checks timed out after {nhc_timeout_sec}s"
        return True, [message], []
    except Exception as e:
        message = f"Could not run LBNL node health checks: {e}"
        return True, [message], []

    # Allow logging to flush
    time.sleep(5)

    def read_log_lines():
        # Return log file as list of lines
        if Path(nhc_log_file).exists():
            return Path(nhc_log_file).read_text().splitlines(), True
        return [], False

    def get_issues(log_lines):
        # Return lines containing WARNING or ERROR
        issues = []
        for line in log_lines:
            stripped = line.strip()
            if stripped.startswith("WARNING:"):
                issues.append(("WARNING", stripped))
            elif stripped.startswith("ERROR:"):
                issues.append(("ERROR", stripped))
        return issues

    # Capture log after running
    nhc_log_output, nhc_log_exists = read_log_lines()
    if not nhc_log_exists:
        message = f"Could not run LBNL node health checks. {nhc_log_file} is not generated."
        return True, [message], []

    issues = get_issues(nhc_log_output)

    if issues:
        warning_messages = [message for level, message in issues if level == "WARNING"]
        error_messages = [message for level, message in issues if level == "ERROR"]
        return len(error_messages) == 0, warning_messages, error_messages
    else:
        logger.info("LBNL node health checks: Passed")
        return True, [], []

#Section 2: Main function and args to run all checks (1.2 - 19.2)
#################################################################

if __name__ == '__main__':
    action = None
    parser = argparse.ArgumentParser(description='Check Host setup')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('-slurm', '--slurm', action='store_true', help='Add a Slurm message')
    parser.add_argument('--dry-run', action='store_true', default=False, help='Skip updating the local files: http-server-file and the log file.')

    parser.add_argument('--oca-stat', action='store_true', help='Check the state of oca')
    parser.add_argument('--instance-rdma-plugins', action='store_true', help='Check if required Instance RDMA plugins are enabled')
    parser.add_argument('--oca-ver', action='store_true', help='Run OCA version check')
    parser.add_argument('--rttcc-stat', action='store_true', help='Run RTTCC status check')
    parser.add_argument('--ecc-err', action='store_true', help='Run ECC errors check')
    parser.add_argument('--rowremap-err', action='store_true', help='Run row remap errors check')
    parser.add_argument('--gpu-count', action='store_true', help='Run GPU count check')
    parser.add_argument('--gpu-pcie', action='store_true', help='Run GPU PCIe check')
    parser.add_argument('--bw-test', dest='bw_test', action='store_true', default=False, help='Run GPU bandwidth test (default: False)')
    parser.add_argument('--bw-test-exe', dest='bw_test_exe', help='Location to cuda-sampels bandwidthTest')
    parser.add_argument('--bus-stat', action='store_true', help='Run bus status check')
    parser.add_argument('--rdmalink-stat', action='store_true', help='Run RDMA link status check')
    parser.add_argument('--rdmalink-flap', action='store_true', help='Run RDMA link flapping check')
    parser.add_argument("--rdma-vf-routes", action="store_true", help="Check MultiPlanar rdma_vf_rail IPv6 addresses/default routes and rdma_p rail IPv6 sequence")
    parser.add_argument("--rdma-vf-counters", action="store_true", help="Check MultiPlanar rdma_vf_rail hardware counters")
    parser.add_argument("--rdma-ovs-mtu", action="store_true", help="Check B300/GB300 MultiPlanar OVS/DPDK RDMA MTU runtime state")
    parser.add_argument("--imex", action="store_true", help="Check NVIDIA IMEX service readiness on GB300 MultiPlanar hosts")
    parser.add_argument('--lf-interval', type=int, default=6, help='Link flapping interval with no flapping or link down events (default: 6 hours)')
    parser.add_argument('--xid-err', action='store_true', help='Run GPU Xid errors check')
    parser.add_argument('--wpa-auth', action='store_true', help='Run WPA authentication check')
    parser.add_argument('--fabric-mgr', action='store_true', help='Run Fabric Manager check')
    parser.add_argument('--cpu-profile', action='store_true', help='Run CPU profile check')
    parser.add_argument('--bad-page', action='store_true', help='Run bad pages check')
    parser.add_argument('--ip-address', action='store_true', help='Check if all interfaces have exactly one IP address')
    parser.add_argument('--nvlink-speed', action='store_true', help='Check NVLinks speeds')
    parser.add_argument('--dcgmi-health', action='store_true', help='Run dcgmi health check')
    parser.add_argument('--rocminfo-check', action='store_true', help='Run rocminfo check')
    parser.add_argument('--lbnl-nhc', action='store_true', help='Run LBNL NHC')

    args = parser.parse_args()
    metadata = get_metadata()
    shape = metadata['shape']
    logger.setLevel(args.log_level)
    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Started GPU host setup check at: {datetime_str}")
    hostname = metadata['displayName']
    ocid = metadata['id']
    # Get host serial number and slurm drain reason
    try:
        host_serial = get_host_serial()
    except Exception as e:
        logger.warning(f"Failed to get host serial number with error: {e}")
        host_serial = "Unknown"
    logger.info(f"Node details: {hostname} - {host_serial} - {shape}")
    logger.info(f"Node details: {ocid}")


#Section 3: Function calls to run all health checks.
####################################################

    # Run everything if no arguments are provided
    run_all = not any(getattr(args, arg) for arg in vars(args) if isinstance(getattr(args, arg), bool) and arg not in ('log_level', 'dry_run')) or args.slurm

    gpu_reset_action = ""
    gpu_reset_status = True

    oca_state = "COMPLETED" if shape in SHAPES_WITHOUT_OCA_STATE_CHECK else None
    oca_dependent_check_requested = (
        run_all
        or args.rttcc_stat
        or args.rdmalink_stat
        or args.rdma_vf_routes
        or args.rdma_ovs_mtu
        or args.rdmalink_flap
        or args.wpa_auth
        or args.ip_address
    )

    # 1.3 Check OCA Status
    if (run_all or args.oca_stat) and (shape not in SHAPES_WITHOUT_OCA_STATE_CHECK):
        try:
            oca_state = check_oca_status(log_state=True)
        except Exception as e:
            logger.warning(f"Failed to check OCA state with error: {e}")
            oca_state = "COMPLETED"

        if oca_state != "COMPLETED":
            logger.error(f"OCA is not ready: {oca_state}")
            slurm_reason("OCA Not completed")

    # 1.5 Check if the RDMA Instance plugins are enabled
    instance_rdma_plugin_issues = []
    if (run_all or args.instance_rdma_plugins) and has_rdma_interfaces():
        try:
            instance_rdma_plugin_issues = check_instance_rdma_plugins()
        except Exception as e:
            logger.warning(f"Failed to check Instance RDMA plugins with error: {e}")
            instance_rdma_plugin_issues = []

    # 2.3 Check for OCA Version
    if run_all or args.oca_ver:
        try:
            oca_version = get_oca_version()
        except Exception as e:
            logger.warning(f"Failed to get Oracle Cloud Agent version with error: {e}")
            oca_version = "Unknown"

    # 3.3 Check for RTTCC Issues (only if OCA status is COMPLETED)
    rttcc_issues = []
    if run_all or args.rttcc_stat:
        if oca_state is None and oca_dependent_check_requested:
            try:
                oca_state = check_oca_status(log_state=False)  # Retrieve OCA state only when needed
            except Exception as e:
                logger.warning(f"Failed to check OCA state with error: {e}")
                oca_state = "NOT STARTED"

        if oca_state == "COMPLETED":
            try:
                rttcc_issues = check_rttcc_status()
            except Exception as e:
                logger.warning(f"Failed to check RTTCC status with error: {e}")
                rttcc_issues = []

    # 4.3 Check for ECC errors
    if (run_all or args.ecc_err) and "GPU" in shape and "BM.GPU.MI" not in shape:
        try:
            ecc_issues = check_ecc_errors()
        except Exception as e:
            logger.warning(f"Failed to check ECC errors with error: {e}")
            ecc_issues = []

    # 5.3 Check for row remap errors
    if (run_all or args.rowremap_err) and "GPU" in shape and "BM.GPU.MI" not in shape:
        try:
            remap_results, row_remap_action = check_row_remap_errors()
        except Exception as e:
            logger.warning(f"Failed to check row remap errors with error: {e}")
            remap_results = []

    # 6.3 Check the number of GPUs
    if run_all or args.gpu_count:
        try:
            gpu_results = check_gpu_count()
        except Exception as e:
            logger.warning(f"Failed to check the number of GPUs with error: {e}")
            gpu_results = None

    # 7.3 Check GPU PCIe width
    if (run_all or args.gpu_pcie) and ( "GPU.GB" not in shape):
        try:
            gpu_pcie_results = check_gpu_pcie()
        except Exception as e:
            logger.warning(f"Failed to check GPU PCIe Width with error: {e}")
            gpu_pcie_results = None

    # 8.3 Check GPU bandwidth
    bwt_results = None
    if args.bw_test:
        try:
           if args.bw_test_exe:
               bwt = BandwidthTest(bw_test_exe=args.bw_test_exe)
           else:
               bwt = BandwidthTest()
           bwt.measure_gpu_bw()
           bwt_results = bwt.validate_results()
        except Exception as e:
            logger.warning(f"Failed to check GPU bandwidth with error: {e}")
            bwt_results = None

    # 9.3 Check for devices fallen off the bus
    if run_all or args.bus_stat:
        try:
            bus_results = check_bus()
        except Exception as e:
            logger.warning(f"Failed to check the bus with error: {e}")
            bus_results = None

    if oca_state is None and oca_dependent_check_requested:
        try:
            oca_state = check_oca_status(log_state=False)
        except Exception as e:
            logger.warning(f"Failed to check OCA state with error: {e}")
            oca_state = "NOT STARTED"

    # 10.3 Check RDMA link status (only if OCA status is COMPLETED)
    if run_all or args.rdmalink_stat:
        if oca_state == "COMPLETED":
            try:
                rdma_link_issues = check_rdma_link_status()
            except Exception as e:
                logger.warning(f"Failed to check RDMA link status with error: {e}")
                rdma_link_issues = []
        else:
            rdma_link_issues = []

    # 10.5 Check MultiPlanar RDMA VF rail address and route state (only if OCA status is COMPLETED)
    if run_all or args.rdma_vf_routes:
        if oca_state == "COMPLETED" and is_multiplanar(shape):
            try:
                rdma_vf_route_issues = check_multiplanar_rdma_vf_routes(metadata)
            except Exception as e:
                logger.warning("Failed to check RDMA VF route state with error: " + str(e))
                rdma_vf_route_issues = []

            try:
                rdma_rail_ipv6_sequence_issues = check_multiplanar_rdma_rail_ipv6_sequence(metadata)
            except Exception as e:
                logger.warning("Failed to check RDMA rail IPv6 sequence with error: " + str(e))
                rdma_rail_ipv6_sequence_issues = []
        else:
            rdma_vf_route_issues = []
            rdma_rail_ipv6_sequence_issues = []

    # 10.6 Check MultiPlanar RDMA VF rail hardware counters
    if run_all or args.rdma_vf_counters:
        if is_multiplanar(shape):
            try:
                rdma_vf_counter_issues = check_multiplanar_rdma_vf_counters(metadata)
            except Exception as e:
                logger.warning("Failed to check RDMA VF counters with error: " + str(e))
                rdma_vf_counter_issues = []
        else:
            rdma_vf_counter_issues = []

    # 10.7 Check B300/GB300 MultiPlanar OVS/DPDK RDMA MTU runtime state
    if run_all or args.rdma_ovs_mtu:
        if oca_state == "COMPLETED" and is_multiplanar(shape):
            try:
                rdma_ovs_mtu_issues = check_multiplanar_rdma_ovs_mtu(metadata)
            except Exception as e:
                logger.warning("Failed to check RDMA OVS MTU state with error: " + str(e))
                rdma_ovs_mtu_issues = []
        else:
            rdma_ovs_mtu_issues = []

    # 10.8 Check NVIDIA IMEX readiness for GB300 MultiPlanar MNNVL
    imex_issues = []
    if run_all or args.imex:
        if "GPU.GB" in shape:
            try:
                imex_issues = check_imex_ready(metadata)
            except Exception as e:
                logger.warning("Failed to check NVIDIA IMEX readiness with error: " + str(e))
                imex_issues = []
        else:
            imex_issues = []

    # 11.3 Check RDMA link flapping (only if OCA status is COMPLETED)
    if run_all or args.rdmalink_flap:
        if oca_state == "COMPLETED":
            try:
                lft = LinkFlappingTest(time_interval=args.lf_interval)
                lft.get_rdma_link_failures()
                lft_issues = lft.process_rdma_link_flapping()
            except Exception as e:
                logger.warning(f"Failed to check RDMA link flapping with error: {e}")
                lft_issues = {"failures": [], "link_down": []}
        else:
            lft_issues = {"failures": [], "link_down": []}

    # 12.3 Check GPU Xid errors
    if run_all or args.xid_err:
        gpu_reset_action = ""
        gpu_reset_status = True
        try:
            xc = XidChecker()
            xid_results = xc.check_gpu_xid()
            xid_categories = xid_results.get("categories", {})
            critical_xids = xid_categories.get("critical", {})
            reset_xids = xid_categories.get("gpu_reset_reboot", {})
            warning_xids  = xid_categories.get("warning", {})
            if critical_xids:
                logger.debug("Xid critical error")
            if reset_xids:
                gpu_reset_action, gpu_reset_status = gpu_reset_reboot(xc)
            if warning_xids:
                logger.debug("Xid warning")
        except Exception as e:
            logger.warning(f"Failed to check GPU Xid errors with error: {e}")
            xid_results = {
                "categories": {
                    "critical": {},
                    "gpu_reset_reboot": {},
                    "warning": {},
                },
                "dmesg_errors": [],
                "results": {},
            }

    # 13.3 Check WPA Authentication status (only if OCA status is COMPLETED)
    if run_all or args.wpa_auth:
        if oca_state == "COMPLETED":
            try:
                wpa_auth_results = check_wpa_auth(metadata)
            except Exception as e:
                logger.warning(f"Failed to get WPA Authentication status: {e}")
                wpa_auth_results = None
        else:
            wpa_auth_results = None

    # 14.3 Check Fabric Manager status
    if run_all or args.fabric_mgr:
        if shape == "BM.GPU.H100.8" or shape == "BM.GPU.H200.8" or shape == "BM.GPU.B200.8":
            try:
                fabric_manager_health = check_fabric_manager()
            except Exception as e:
                logger.warning(f"Failed to check Fabric Manager with error: {e}")
                fabric_manager_health = True

            if fabric_manager_health:
                logger.info("Fabric Manager Running: Passed")
        else:
            fabric_manager_health = True

    # 15.3 Check if CPU profile is performance
    if run_all or args.cpu_profile:
        try:
            cpu_profile_issues = get_current_cpu_profile()
        except Exception as e:
            logger.warning(f"Failed to check CPU profile with error: {e}")
            cpu_profile_issues = []

    # 16.3 Check if AMD GPU has pending bad pages
    if run_all or args.bad_page:
        try:
            if "BM.GPU.MI" in shape:
                bad_page_issues = check_bad_pages()
            else:
                bad_page_issues = None
        except Exception as e:
            logger.warning(f"Failed to check pending bad pages: {e}")
            bad_page_issues = []

    # 17.3 Check if required RDMA interfaces have valid IP addresses
    if (run_all or args.ip_address) and should_check_ip_addresses(shape):
        if oca_state == "COMPLETED":
            try:
                missing_ips,multiple_ips,ip_list = check_ip_addresses()
                if len(missing_ips) == 0 and len(multiple_ips) == 0:
                    logger.info("Required RDMA interfaces have valid IP addresses: Passed")
            except Exception as e:
                logger.warning(f"Failed to get all IPS: {e}")
                missing_ips = []
                multiple_ips = []
        else:
            missing_ips = []
            multiple_ips = []

    # 18.3 Check if NVLink speed is correct
    if (run_all or args.nvlink_speed) and (shape not in ["BM.GPU.L40S-NC.4", "BM.GPU.MI300X.8", "BM.GPU.MI355X.8", "BM.GPU.MI355X-v0.8", "BM.GPU.MI355X-v1.8", "BM.GPU.A10.4", "BM.GPU.RTXPRO.8"]):
        nvlink_speed = get_nvlink_speed()
    else:
        nvlink_speed = True

    # 19.3 Check the node health using dcgmi health check
    if run_all or args.dcgmi_health:
        if "BM.GPU.MI" not in shape:
            try:
                dcgmi_health_check, dcgmi_health_warnings, dcgmi_health_errors = run_dcgmi_health()
                if dcgmi_health_warnings:
                    logger.warning(f"{host_serial} - dcgmi warnings:\n" + "\n".join(dcgmi_health_warnings))
                if dcgmi_health_errors:
                    logger.error(f"{host_serial} - dcgmi errors:\n" + "\n".join(dcgmi_health_errors))
                if dcgmi_health_check:
                    logger.info("dcgmi health check: Passed")
            except Exception as e:
                logger.warning(f"Failed to run dcgmi health check with error: {e}")
                dcgmi_health_check = True
                dcgmi_health_warnings = []
                dcgmi_health_errors = []
        else:
            dcgmi_health_check = True
            dcgmi_health_warnings = []
            dcgmi_health_errors = []

    # 20.3 Validate rocminfo is valid or not
    if run_all or args.rocminfo_check:
        if "BM.GPU.MI" in shape:
            try:
                rocminfo_check = run_rocminfo_check()
            except Exception as e:
                logger.warning(f"Failed to run rocminfo health check with error: {e}")
                rocminfo_check = True
            if rocminfo_check:
                logger.info("rocminfo health check: Passed")
        else:
            rocminfo_check = True

    # 21.3 Check the node health using LBNL NHC
    if run_all or args.lbnl_nhc:
        try:
            lbnl_nhc_output, lbnl_nhc_warnings, lbnl_nhc_errors = run_nhc_check()
            if lbnl_nhc_warnings:
                logger.warning(
                f"{host_serial} - LBNL node health check warnings:\n" + "\n".join(lbnl_nhc_warnings)
            )
            if lbnl_nhc_errors:
                logger.error(
                f"{host_serial} - LBNL node health check errors:\n" + "\n".join(lbnl_nhc_errors)
            )
        except Exception as e:
            logger.warning(f"Failed to run LBNL node health check with error: {e}")
            lbnl_nhc_output = True
            lbnl_nhc_warnings = []
            lbnl_nhc_errors = []

#Section 4: Summarize the results and recommend actions.
########################################################

    logger.info(f"--------- Summary of Host setup check for {host_serial} ---------")

    # 1.4 Summarize OCA status check
    if (run_all or args.oca_stat) and (shape not in SHAPES_WITHOUT_OCA_STATE_CHECK):
        if oca_state != "COMPLETED":
            logger.error(f"OCA is not ready: {oca_state}")
            slurm_reason("OCA Not completed")
            action = recommended_action(action, "Wait_For_OCA")

    # 1.6 Summarize Instance RDMA plugins check
    if (run_all or args.instance_rdma_plugins) and has_rdma_interfaces():
        if len(instance_rdma_plugin_issues) > 0:
            for issue in instance_rdma_plugin_issues:
                logger.error(f"{host_serial} - Instance RDMA plugin issue: {issue}")
            slurm_reason("Instance RDMA Plugin Status Error")
            action = recommended_action(action, "Enable_Instance_RDMA_Plugins")

    # 2.4 Summarize OCA version check
    if run_all or args.oca_ver:
        if oca_version < "1.39.0":
            logger.error(f"Oracle Cloud Agent: {oca_version} needs to be updated to 1.39.0 or higher")
            slurm_reason("OCA version Error")

    # 3.4 Summarize RTTCC status check
    if run_all or args.rttcc_stat:
        if "BM.GPU.MI" not in shape:
            if len(rttcc_issues) > 0:
                logger.error(f"RTTCC issues: {rttcc_issues}")
                slurm_reason("RTTCC Error")

    # 4.4 Summarize ECC errors check
    if (run_all or args.ecc_err) and "GPU" in shape and "BM.GPU.MI" not in shape:
        if len(ecc_issues) > 0:
            ecc_error = False
            for issue in ecc_issues:
                if "Skipped" in issue or "timed out after" in issue:
                    logger.warning(f"{host_serial} - {issue}")
                elif "Aggregate" in issue:
                    logger.warning(f"{host_serial} - ECC issues: {issue}")
                else:
                    logger.error(f"{host_serial} - ECC issues: {issue}")
                    ecc_error = True
            if ecc_error:
                slurm_reason("ECC Error")
                action = recommended_action(action, "Reboot")

    # 5.4 Summarize row remap errors check
    if (run_all or args.rowremap_err) and "GPU" in shape and "BM.GPU.MI" not in shape:
        if len(remap_results) > 0:
            remap_error = False
            for issue in remap_results:
                if "<512" in issue or "timed out after" in issue:
                    logger.warning(f"{host_serial} - {issue}")
                else:
                    logger.error(f"{host_serial} - {issue}")
                    remap_error = True
            if remap_error:
                slurm_reason("Remap Error")
                action = recommended_action(action, row_remap_action)

    # 6.4 Summarize GPU count check
    if run_all or args.gpu_count:
        if gpu_results:
            logger.error(f"{host_serial} - Missing GPU(s): {gpu_results}")
            slurm_reason("Missing GPU Error")
            action = recommended_action(action, "Reboot")

    # 7.4 Summarize GPU PCIe width check
    if (run_all or args.gpu_pcie) and ( "GPU.GB" not in shape):
            if gpu_pcie_results:
                logger.error(f"{host_serial} - GPU PCIe Width: {gpu_pcie_results}")
                slurm_reason("GPU PCIe Width Error")
                action = recommended_action(action, "Terminate")

    # 8.4 Summarize GPU bandwidth test
    if run_all or args.bw_test:
        if bwt_results is not None:
            if bwt_results["status"] == "Failed":
                for issue in bwt_results["issues"]:
                    logger.error(f"{host_serial} - GPU bandwidth issues: {issue}")
                    slurm_reason("GPU Bwt Error")

    # 9.4 Summarize bus status check
    if run_all or args.bus_stat:
        if bus_results:
            logger.error(f"{host_serial} - Bus issues: {bus_results}")
            slurm_reason("GPU Bus Error")
            action = recommended_action(action, "Terminate")

    # 10.4 Summarize RDMA link status check
    if run_all or args.rdmalink_stat:
        if len(rdma_link_issues) > 0:
            for issue in rdma_link_issues:
                logger.error(f"{host_serial} - RDMA link issues: {issue}")
                slurm_reason("RDMA Link down")
                if "signal not detected" in issue:
                    logger.info("No signal detected doesn't always come from a bad cable and require a termination for investigation")
                action = recommended_action(action, "Terminate")

    # 10.5 Summarize MultiPlanar RDMA VF rail address and route state
    if run_all or args.rdma_vf_routes:
        if len(rdma_vf_route_issues) > 0:
            for issue in rdma_vf_route_issues:
                logger.error(host_serial + " - RDMA VF route issues: " + issue)
            slurm_reason("RDMA Route Missing")
            action = recommended_action(action, "Reboot")

    # 10.6 Summarize MultiPlanar RDMA rail IPv6 sequence
    if run_all or args.rdma_vf_routes:
        if len(rdma_rail_ipv6_sequence_issues) > 0:
            for issue in rdma_rail_ipv6_sequence_issues:
                logger.error(host_serial + " - RDMA rail IPv6 sequence issues: " + issue)
            slurm_reason("RDMA Rail IPv6 Sequence Error")
            action = recommended_action(action, "Wait_For_OCA")

    # 10.7 Summarize MultiPlanar RDMA VF rail hardware counters
    if run_all or args.rdma_vf_counters:
        if len(rdma_vf_counter_issues) > 0:
            for issue in rdma_vf_counter_issues:
                logger.error(host_serial + " - RDMA VF counter issues: " + issue)
            slurm_reason("RDMA VF Counter Error")
            action = recommended_action(action, "Terminate")

    # 10.8 Summarize B300/GB300 MultiPlanar OVS/DPDK RDMA MTU runtime state
    if run_all or args.rdma_ovs_mtu:
        if len(rdma_ovs_mtu_issues) > 0:
            for issue in rdma_ovs_mtu_issues:
                logger.error(host_serial + " - RDMA OVS MTU issues: " + issue)
            slurm_reason("RDMA OVS MTU Error")
            action = recommended_action(action, "Reboot")

    # 10.9 Summarize NVIDIA IMEX readiness check
    if run_all or args.imex:
        if len(imex_issues) > 0:
            for issue in imex_issues:
                logger.error(host_serial + " - IMEX issues: " + issue)
            slurm_reason("IMEX Error")
            action = recommended_action(action, "Reboot")

    # 11.4 Summarize RDMA link flapping check
    if run_all or args.rdmalink_flap:
        if len(lft_issues["failures"]) > 0 or len(lft_issues["link_down"]) > 0:
           if len(lft_issues["failures"]) == 1:
              issue = lft_issues["failures"][0]
              logger.warning(f"{host_serial} - RDMA authentication flap issues: {issue}")
              slurm_reason("RDMA Auth flap")
           elif len(lft_issues["failures"]) > 1:
              for issue in lft_issues["failures"]:
                  logger.error(f"{host_serial} - RDMA authentication flap issues: {issue}")
                  slurm_reason("RDMA Auth flap")
           if len(lft_issues["link_down"]) == 1:
              issue = lft_issues["link_down"][0]
              logger.warning(f"{host_serial} - RDMA link carrier flap issues: {issue}")
              slurm_reason("RDMA Link flap")
           elif len(lft_issues["link_down"]) > 1:
              for issue in lft_issues["link_down"]:
                  logger.error(f"{host_serial} - RDMA link carrier flap issues: {issue}")
                  slurm_reason("RDMA Link flap")

    # 12.4 Summarize GPU Xid errors check
    if run_all or args.xid_err:
        xid_categories = xid_results.get("categories", {})
        critical_xids = xid_categories.get("critical", {})
        reset_xids = xid_categories.get("gpu_reset_reboot", {})
        warning_xids  = xid_categories.get("warning", {})
        dmesg_errors = xid_results.get("dmesg_errors", [])

        # Log & set action for Xids
        if dmesg_errors:
            action = recommended_action(action, "Terminate")
            for issue in dmesg_errors:
                logger.error(f"{host_serial} - {issue}")
                slurm_reason("Multicast Error")
        if critical_xids:
            action = recommended_action(action, "Terminate")
            for xid, info in critical_xids.items():
                desc = info["description"]
                for pci, count in info["results"].items():
                    logger.error(
                        f"{host_serial} - [critical] GPU Xid {xid} "
                        f"device: {pci}, count: {count}, {desc}"
                    )
                    slurm_reason("Xid Error")
        if reset_xids:
            if not gpu_reset_status:
                if gpu_reset_action == "Reboot":
                    action = recommended_action(action, "Reboot")
                    slurm_reason("Xid Error")
                elif gpu_reset_action == "Terminate":
                    action = recommended_action(action, "Terminate")
                    slurm_reason("Xid Error")
                elif gpu_reset_action == "GPU_Reset":
                    action = recommended_action(action, "Reset_GPU")
                    slurm_reason("Reset_GPU")
                else:
                    action = recommended_action(action, "Reboot")
                    slurm_reason("Xid Error")
                if gpu_reset_action != "":
                    for xid, info in reset_xids.items():
                        desc = info["description"]
                        for pci, count in info["results"].items():
                            logger.error(
                                f"{host_serial} - [gpu_reset_reboot] GPU Xid {xid} "
                                f"device: {pci}, count: {count}, {desc}"
                            )
        if warning_xids:
            for xid, info in warning_xids.items():
                desc = info["description"]
                for pci, count in info["results"].items():
                    logger.warning(
                        f"{host_serial} - [warning] GPU Xid {xid} "
                        f"device: {pci}, count: {count}, {desc}"
                    )

    # 13.4 Summarize WPA Authentication check
    if run_all or args.wpa_auth:
        if wpa_auth_results:
            for issue in wpa_auth_results:
                logger.error(f"{host_serial} - WPA authentication issue: {issue}")
            slurm_reason("WPA Auth Error")
            action = recommended_action(action, "Reboot")

    # 14.4 Summarize Fabric Manager check
    if run_all or args.fabric_mgr:
        if not fabric_manager_health:
            logger.error(f"{host_serial} - Fabric Manager not started")
            slurm_reason("Fabric Manager Error")
            action = recommended_action(action, "FabricManagerRestart")

    # 15.4 Summarize CPU profile check
    if run_all or args.cpu_profile:
        if cpu_profile_issues:
            logger.warning("CPU Profile need to be 'performance'.")
            #for issue in cpu_profile_issues:
            #    logger.error(f" - {issue}")
            #slurm_reason("CPU Profile error")
            #action = recommended_action(action, "Terminate")

    # 16.4 Summarize pending bad pages check for AMD
    if run_all or args.bad_page:
        if bad_page_issues:
            for issue in bad_page_issues:
                logger.error(f"{host_serial} - GPU has pending bad pages: {issue}")
            slurm_reason("GPU Bad page error")
            action = recommended_action(action, "Reboot")

    # 17.4 Summarize required RDMA interfaces have valid IP addresses check
    if (run_all or args.ip_address) and should_check_ip_addresses(shape):
        if len(missing_ips) > 0:
            logger.error(f"Missing IPs for these interfaces: {','.join(missing_ips)}")
            slurm_reason("RDMA Missing IP")
            action = recommended_action(action, "Reboot")
        if len(multiple_ips) > 0:
            logger.error(f"Multiple IPs for these interfaces: {','.join(multiple_ips)}")
            slurm_reason("Multiple IPs")
            action = recommended_action(action, "Reboot")

    # 18.4 Summarize NVLink speed check
    if run_all or args.nvlink_speed:
        if not nvlink_speed:
            logger.error("NVLink speed Error for one or more GPUs")
            slurm_reason("NVLink speed Error")
            action = recommended_action(action, "Reboot")

    # 19.4 Summarize dcgmi health check
    if run_all or args.dcgmi_health:
        if dcgmi_health_errors:
            logger.error(f"{host_serial} - dcgmi errors:\n" + "\n".join(dcgmi_health_errors))
        if not dcgmi_health_check:
            slurm_reason("dcgmi health check failed")
            action = recommended_action(action, "Reboot")

    # 20.4 Summarize rocminfo health check
    if run_all or args.rocminfo_check:
        if not rocminfo_check:
            logger.error(f"{host_serial} - rocminfo health check failed")
            slurm_reason("rocminfo health check failed")
            action = recommended_action(action, "Reboot")

    # 21.4 Summarize LBNL node health check
    if run_all or args.lbnl_nhc:
        if lbnl_nhc_errors:
            logger.error(
                f"{host_serial} - LBNL node health check errors:\n" + "\n".join(lbnl_nhc_errors)
            )
        if not lbnl_nhc_output:
            if not lbnl_nhc_errors:
                logger.error(
                    f"{host_serial} - LBNL node health check failed. Check /var/log/nhc.log for details."
                )
            slurm_reason("LBNL node health check failed")
            action = recommended_action(action, "Check_nhc_log")

    # Print recommended action and slurm message
    if action == "Reboot":
        number_of_reboots,last_2hour_reboot,last_12hour_reboot = get_reboots_count()
        if last_2hour_reboot > 0 or number_of_reboots > 5:
            action = "Terminate"
            logger.error(f"The node has already been rebooted {last_2hour_reboot} time(s) in the last 2 hours and {number_of_reboots} in the last day")
        else:
            logger.error("Recommended Action is to Force Reboot from the console or API")
    if action == "Terminate":
        logger.error("Recommended Action is to Tag the node Unhealthy and Terminate the node")
    if action == "Wait_For_OCA":
        logger.error("Recommended Action is to wait for OCA to finish configuring. If it has been more than 10 minutes, try rebooting the node")

    if slurm_error_count > 0 and any((args.slurm, args.dry_run)):
        logger.error("Healthcheck:: " + format_healthcheck_status(slurm_drain_reason))
        logger.error("Healthcheck:: Recommended Action:" + str(action))

    logger.info(f"Finished GPU host setup check at: {datetime_str}")

    if not args.dry_run:
        http_server_file="/opt/oci-hpc/http_server/files/healthchecks"
        # Read the existing data from the file
        try:
            with open(http_server_file, 'r') as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.debug("Error: File not found or not in valid JSON format.")
            data={}
    else:
        data = {}
    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    if action is None:
        data["passive_healthcheck_recommendation"] = "Healthy"
    else:
        data["passive_healthcheck_recommendation"] = action
    data["passive_healthcheck_time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    # Read the healthcheck.log file content
    if not args.dry_run:
        try:
            with open("/var/log/healthchecks/latest_healthcheck.log", 'r') as log_file:
                data["passive_healthcheck_logs"] = log_file.read(4095)  # Store log content in JSON
        except FileNotFoundError:
            logger.warning("Log file not found, initializing empty logs.")
            data["passive_healthcheck_logs"] = ""
        data["passive_healthcheck_status"] = format_healthcheck_status(slurm_drain_reason)
        # Write updated data back to the file
        with open(http_server_file, 'w') as file:
            try:
                json.dump(data, file, indent=4)
            except Exception as e:
                logger.error(f"Error writing to file: {e}")
