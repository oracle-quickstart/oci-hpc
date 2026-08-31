#!/usr/bin/env python3
import sys
import os
import argparse
import json
import requests
import subprocess
import logging
import glob
import shlex
import time
import re

# Configure logger for multi_node_active_healthcheck
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('multi_node_active_healthcheck')

version = sys.version_info
if version >= (3, 12):
    from datetime import datetime, UTC
else:
    from datetime import datetime

GB_SHAPES = {
    "BM.GPU.GB200.4",
    "BM.GPU.GB200-v2.4",
    "BM.GPU.GB200-v3.4",
    "BM.GPU.GB300.4",
}

MULTIPLANAR_RDMA_VF_COUNTS = {
    "BM.GPU.B300.8": 8,
    "BM.GPU.B300.HS.8": 8,
    "BM.GPU.GB300.4": 4,
}

GB300_MULTIPLANAR_NCCL_TOPO_FILE = "/opt/oci-hpc/healthchecks/GB300MP.xml"
B300_MULTIPLANAR_NCCL_TOPO_FILE = "/opt/oci-hpc/healthchecks/B300MP.xml"

MULTIPLANAR_RDMA_VF_SETTINGS = {
    "rdma_vf_rail0": {"vrf": "vrf_r0", "port": "18001", "cuda_bus": "00000009:06:00.0"},
    "rdma_vf_rail1": {"vrf": "vrf_r1", "port": "18002", "cuda_bus": "00000008:06:00.0"},
    "rdma_vf_rail2": {"vrf": "vrf_r2", "port": "18003", "cuda_bus": "00000019:06:00.0"},
    "rdma_vf_rail3": {"vrf": "vrf_r3", "port": "18004", "cuda_bus": "00000018:06:00.0"},
}

B300_MULTIPLANAR_RDMA_VF_SETTINGS = {
    "rdma_vf_rail0": {"vrf": "vrf_r0", "port": "18001", "cuda_bus": "00000014:00.0"},
    "rdma_vf_rail1": {"vrf": "vrf_r1", "port": "18002", "cuda_bus": "00000032:00.0"},
    "rdma_vf_rail2": {"vrf": "vrf_r2", "port": "18003", "cuda_bus": "00000049:00.0"},
    "rdma_vf_rail3": {"vrf": "vrf_r3", "port": "18004", "cuda_bus": "00000060:00.0"},
    "rdma_vf_rail4": {"vrf": "vrf_r4", "port": "18005", "cuda_bus": "0000008E:00.0"},
    "rdma_vf_rail5": {"vrf": "vrf_r5", "port": "18006", "cuda_bus": "000000AD:00.0"},
    "rdma_vf_rail6": {"vrf": "vrf_r6", "port": "18007", "cuda_bus": "000000C5:00.0"},
    "rdma_vf_rail7": {"vrf": "vrf_r7", "port": "18008", "cuda_bus": "000000DD:00.0"},
}

# Set defaults
# IMPORTANT: when adding var_NCCL_IB_HCA, make sure it has "=" sign in the front and the values are comma-separated with no extra space around the comma
shape_mapping = {
    "BM.GPU.B4.8": {
        "var_UCX_NET_DEVICES": "mlx5_0:1",
        "var_NCCL_IB_HCA": "=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12",
        "threshold": 185,
        "ib_write_bw": 96,
        "ib_write_lat": 5
    },
    "BM.GPU.A100-v2.8": {
        "var_UCX_NET_DEVICES": "mlx5_0:1",
        "var_NCCL_IB_HCA": "=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12",
        "threshold": 185,
        "ib_write_bw": 96,
        "ib_write_lat": 5
    },
    "BM.GPU4.8": {
        "var_UCX_NET_DEVICES": "mlx5_4:1",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_2,mlx5_6,mlx5_8,mlx5_10,mlx5_12,mlx5_14,mlx5_16,mlx5_1,mlx5_3,mlx5_7,mlx5_9,mlx5_11,mlx5_13,mlx5_15,mlx5_17",
        "threshold": 185,
        "ib_write_bw": 96,
        "ib_write_lat": 5
    },
    "BM.GPU.H100.8": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17",
        "threshold": 440,
        "ib_write_bw": 192,
        "ib_write_lat": 5
    },
    "BM.GPU.H200.8": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11",
        "threshold": 440,
        "ib_write_bw": 384,
        "ib_write_lat": 5
    },
    "BM.GPU.B300.8": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_11,mlx5_12,mlx5_13,mlx5_14,mlx5_16,mlx5_17,mlx5_18,mlx5_19,mlx5_20,mlx5_21",
        "threshold": 700,
        "ib_write_bw": 375,
        "ib_write_lat": 5
    },
    "BM.GPU.B300.HS.8": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_11,mlx5_12,mlx5_13,mlx5_14,mlx5_16,mlx5_17,mlx5_18,mlx5_19,mlx5_20,mlx5_21",
        "threshold": 700,
        "ib_write_bw": 375,
        "ib_write_lat": 5
    },
    "BM.GPU.RTXPRO.8": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_6,mlx5_7,mlx5_8,mlx5_9",
        "iterations": 10,
        "threshold": 20,  # The RTXPRO are connected to the NICs via PCIe and slow
        "ib_write_bw": 375,
        "ib_write_lat": 5
    },
    "BM.GPU.B200.8": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11",
        "threshold": 440,
        "ib_write_bw": 384,
        "ib_write_lat": 5
    },
    "BM.GPU.GB200.4": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_3,mlx5_4",
        "ib_write_bw": 384,
        "ib_write_lat": 9
    },
    "BM.GPU.GB200-v2.4": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_3,mlx5_4",
        "ib_write_bw": 384,
        "ib_write_lat": 9
    },
    "BM.GPU.GB200-v3.4": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8",
        "ib_write_bw": 384,
        "ib_write_lat": 9,
        "threshold": 300
    },
    "BM.GPU.GB300.4": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8",
        "ib_write_bw": 384,
        "ib_write_lat": 9,
        "threshold": 440,
        "mnnvl_disabled_threshold": 600,
    },
    "BM.Optimized3.36": {
        "var_UCX_NET_DEVICES": "eth0",
        "var_NCCL_IB_HCA": "=mlx5_2",
        "ib_write_bw": 96,
        "ib_write_lat": 5
    },
    "BM.GPU.MI300X.8": {
        "var_UCX_NET_DEVICES": "mlx5_0:1",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_7,mlx5_8,mlx5_9",
        "threshold": 350,
        "ib_write_bw": 350,
        "ib_write_lat": 5
    },
    "BM.GPU.MI355X.8": {
        "var_UCX_NET_DEVICES": "mlx5_8:1",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7",
        "threshold": 350,
        "ib_write_bw": 350,
        "ib_write_lat": 5
    },
    "BM.GPU.MI355X-v0.8": {
        "var_UCX_NET_DEVICES": "mlx5_8:1",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7",
        "threshold": 350,
        "ib_write_bw": 350,
        "ib_write_lat": 5
    },
    "BM.GPU.MI355X-v1.8": {
        "var_UCX_NET_DEVICES": "mlx5_8:1",
        "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7",
        "threshold": 350,
        "ib_write_bw": 350,
        "ib_write_lat": 5
    }
}

healthy = "Healthy"
potentially_bad = "Potentially Bad"
bad = "Bad"
ib_write_lat_threshold = 5

def get_metadata():
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()

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

def rdma_rail_sort_key(device):
    match = re.search(r'(\d+)$', device)
    if match:
        return int(match.group(1))
    return device

def discover_existing_multiplanar_rdma_devices():
    try:
        devices = os.listdir("/sys/class/infiniband")
    except FileNotFoundError:
        return []

    return sorted(
        [device for device in devices if re.match(r'^rdma_vf_rail\d+$', device)],
        key=rdma_rail_sort_key
    )

def discover_multiplanar_rdma_devices(shape):
    vf_rails = discover_existing_multiplanar_rdma_devices()
    if vf_rails:
        return vf_rails

    return [
        f"rdma_vf_rail{i}"
        for i in range(MULTIPLANAR_RDMA_VF_COUNTS.get(shape, 0))
    ]

def is_gb300_multiplanar(shape):
    return (
        shape == "BM.GPU.GB300.4"
        and (get_rdma_planes() > 1 or bool(discover_existing_multiplanar_rdma_devices()))
    )

def is_b300_multiplanar(shape):
    return (
        shape in ("BM.GPU.B300.8", "BM.GPU.B300.HS.8")
        and (get_rdma_planes() > 1 or bool(discover_existing_multiplanar_rdma_devices()))
    )

def apply_shape_overrides(shape):
    global MULTIPLANAR_RDMA_VF_SETTINGS

    if is_b300_multiplanar(shape):
        rdma_vf_devices = discover_multiplanar_rdma_devices(shape)
        MULTIPLANAR_RDMA_VF_SETTINGS = B300_MULTIPLANAR_RDMA_VF_SETTINGS
        shape_mapping[shape].update({
            "var_UCX_NET_DEVICES": "eth0",
            "var_NCCL_IB_HCA": ",".join(rdma_vf_devices),
            "ib_write_bw": 170,
            "threshold": 700,
            "multiplanar": True,
        })
        logger.info(f"Using B300 MultiPlanar RDMA VF devices: {rdma_vf_devices}")

    if is_gb300_multiplanar(shape):
        rdma_vf_devices = discover_multiplanar_rdma_devices(shape)
        shape_mapping[shape].update({
            "var_UCX_NET_DEVICES": "eth0",
            "var_NCCL_IB_HCA": ",".join(rdma_vf_devices),
            "ib_write_bw": 770,
            "threshold": 800,
            "multiplanar": True,
        })
        logger.info(f"Using GB300 MultiPlanar RDMA VF devices: {rdma_vf_devices}")

# Check if the user is root
def is_user_root():
    if os.geteuid() != 0:
        logger.debug("User is not root!")
        return False
    return True

def get_host_serial():
    try:
        # Try dmidecode first (Only works on BM instances)
        cmd = ['sudo', 'dmidecode', '-s', 'system-serial-number'] if not is_user_root() else ['dmidecode', '-s', 'system-serial-number']
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        serial_number = result.stdout.decode('utf-8').strip()

        # If dmidecode output is empty, "Not Specified", or failed, assume it's a VM
        if result.returncode == 0 and serial_number != "Not Specified":
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

def custom_join(cmd_list):
    return ' '.join(('^hcoll' if x == '^hcoll' else shlex.quote(x)) for x in cmd_list)

def get_node_details():
    try:
        host_serial = get_host_serial()
    except Exception as e:
        logger.warning(f"Failed to get host serial number with error: {e}")
        host_serial = "Unknown"
    logger.info(f"Node details: {hostname} - {host_serial} - {ocid} - {shape}")

def is_gb_shape(shape):
    return shape in GB_SHAPES or "GPU.GB" in shape

def get_remote_json(host, command, timeout=15):
    try:
        result = subprocess.run(
            ["ssh", host, command],
            timeout=timeout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.debug(f"Could not read remote JSON from {host}: {e}")
        return {}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.debug(f"Could not parse remote JSON from {host}: {result.stdout[:200]}")
        return {}

def get_node_rack_id(host):
    metadata_command = "curl -fsS -H 'Authorization: Bearer Oracle' http://169.254.169.254/opc/v2/host 2>/dev/null"
    info_command = "cat /opt/oci-hpc/http_server/files/info 2>/dev/null"

    for command in (metadata_command, info_command):
        data = get_remote_json(host, command)
        rack_id = data.get("rackId") or data.get("rack_id")
        if rack_id and rack_id != "None":
            return rack_id

    logger.warning(f"Could not determine rack ID for {host}")
    return None

def hosts_share_rack(client_host, server_host):
    client_rack = get_node_rack_id(client_host)
    server_rack = get_node_rack_id(server_host)
    same_rack = bool(client_rack and server_rack and client_rack == server_rack)
    logger.info(
        f"Rack comparison: {client_host}={client_rack or 'unknown'}, "
        f"{server_host}={server_rack or 'unknown'}, same_rack={same_rack}"
    )
    return same_rack

def get_gb_mnnvl_test_values(client_host=None, server_host=None):
    if client_host and server_host and hosts_share_rack(client_host, server_host):
        logger.info("GB hosts are in the same rack; running NCCL with MNNVL=1 and MNNVL=0")
        return [1, 0]

    logger.info("GB hosts are not in the same rack or rack could not be verified; running only NCCL with MNNVL=0")
    return [0]

def is_multiplanar_rdma_vf_device(device):
    return device in MULTIPLANAR_RDMA_VF_SETTINGS

def get_multiplanar_ib_command(cmd_base, device, shape=None, use_cuda=False):
    settings = MULTIPLANAR_RDMA_VF_SETTINGS.get(device)
    if not settings:
        return f"{cmd_base} -d {shlex.quote(device)}"

    cmd = [
        "sudo",
        "ip",
        "vrf",
        "exec",
        settings["vrf"],
        *shlex.split(cmd_base),
    ]
    if use_cuda:
        cmd.extend([
            f"--use_cuda_bus_id={settings['cuda_bus']}",
            "--use_cuda_dmabuf",
        ])
        if shape not in ("BM.GPU.B300.8", "BM.GPU.B300.HS.8"):
            cmd.append("--use_data_direct")
    cmd.extend(["-d", device, "-p", settings["port"]])
    return shlex.join(cmd)

def get_ipv6_for_ib_device(host, device):
    remote_cmd = (
        f"dev={shlex.quote(device)}; "
        "netdev=\"$dev\"; "
        "if [ -d \"/sys/class/infiniband/$dev/device/net\" ]; then "
        "found=$(ls \"/sys/class/infiniband/$dev/device/net\" 2>/dev/null | head -n 1); "
        "[ -n \"$found\" ] && netdev=\"$found\"; "
        "fi; "
        "ip -6 -o addr show dev \"$netdev\" scope global 2>/dev/null | "
        "awk '{split($4,a,\"/\"); print a[1]; exit}'"
    )
    try:
        result = subprocess.run(
            ["ssh", host, remote_cmd],
            timeout=15,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logger.warning(f"{host} {device}: failed to read IPv6 address: {e}")
        return ""

    return result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""

def run_nccl_test_case(mpivars_path, mpirun_cmd, shape, label, mnnvl_enable=None):
    mpirun_str = custom_join(mpirun_cmd)
    cmd = f"source {mpivars_path} && {mpirun_str}"

    for attempt in range(1, 6):
        logger.info(f"{label} Test {attempt}/5")
        try:
            result = subprocess.run(
                ["/bin/bash", "-c", cmd],
                text=True,
                timeout=120,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except subprocess.TimeoutExpired:
            return False, f"{label} Failed: NCCL test timed out after 2 minutes"
        except Exception as e:
            error_text = str(e)
            if ("Invalid number of GPUs" in error_text or "invalid device ordinal" in error_text) and attempt < 5:
                continue
            return False, f"{label} Failed: Failed to run NCCL test. {e}"

        if result.returncode == 0:
            bw = None
            shape_config = shape_mapping.get(shape, {})
            threshold = shape_config.get("threshold", 0) or 0
            if mnnvl_enable == 0:
                threshold = shape_config.get("mnnvl_disabled_threshold", threshold) or 0
            for line in result.stdout.splitlines():
                if "Avg bus bandwidth" in line:
                    try:
                        bw = float(line.split()[5])
                    except (IndexError, ValueError):
                        return False, f"{label} Failed: Avg bus bandwidth could not be parsed"
                    logger.info(
                        f"{label}: NCCL Avg bus bandwidth is {bw} GB/s "
                        f"(threshold: {threshold or 'not set'} GB/s)"
                    )
                    if threshold and bw < threshold:
                        return False, f"{label} Failed: Avg bus bandwidth is {bw} which is less than {threshold}"
            if bw is not None:
                return True, f"{label} Succeeded: Avg bus bandwidth is {bw}"
            return False, f"{label} Failed: Avg bus bandwidth could not be found"

        invalid_gpu = (
            "Invalid number of GPUs" in result.stdout
            or "Invalid number of GPUs" in result.stderr
            or "invalid device ordinal" in result.stdout
            or "invalid device ordinal" in result.stderr
        )
        if invalid_gpu and attempt < 5:
            continue
        return False, f"{label} Failed: Failed to run NCCL test. {result.stdout},{result.stderr}"

    return False, f"{label} Failed: NCCL test failed after 5 attempts"

def run_multi_node_nccl_test(hostfile, shape, client_host=None, server_host=None):
    apply_shape_overrides(shape)
    paths = glob.glob('/usr/mpi/gcc/openmpi-*/bin/mpivars.sh')
    if paths:
        mpivars_path = paths[0]
    else:
        logger.info("157")

        return False,"NCCL Test Failed: No mpivars.sh found"

    increment=1024*1024*1024*9
    NCCL_DEBUG="WARN"
    exec_cmd="/opt/oci-hpc/nccl-test/build/all_reduce_perf"

    iterations = shape_mapping.get(shape, {}).get("iterations", 50)
    var_UCX_NET_DEVICES = shape_mapping.get(shape, {}).get('var_UCX_NET_DEVICES', '')
    if var_UCX_NET_DEVICES == "":
        logger.info("166")
        return False,f"NCCL Test Failed: Shape {shape} not found for NCCL test"
    var_NCCL_IB_HCA = shape_mapping.get(shape, {}).get('var_NCCL_IB_HCA', '')
    multiplanar = shape_mapping.get(shape, {}).get("multiplanar", False)
    nccl_test_cases = []
    if shape in ("BM.GPU.B4.8", "BM.GPU.A100-v2.8", "BM.GPU4.8"):
        logger.info("170")
        mpirun_cmd = [
            "mpirun", "--mca", "pml", "ucx",
            "--bind-to", "numa",
            "--mca", "coll", "^hcoll",
            "--mca", "plm_rsh_no_tree_spawn", "1",
            "-x", "UCX_TLS=ud,self,sm",
            "-x", f"UCX_NET_DEVICES={var_UCX_NET_DEVICES}",
            "-x", f"NCCL_IB_HCA={var_NCCL_IB_HCA}",
            "-x", "HCOLL_ENABLE_MCAST_ALL=0",
            "-x", "coll_hcoll_enable=0",
            "-x", "NCCL_ALGO=Ring",
            "-x", f"NCCL_DEBUG={NCCL_DEBUG}",
            "-x", "NCCL_IB_SL=0",
            "-x", "NCCL_IB_TC=41",
            "-x", "NCCL_IB_QPS_PER_CONNECTION=4",
            "-x", "NCCL_IB_GID_INDEX=3",
            "--np", "16",
            "--rankfile", hostfile,
            "bash","-c",
            f"{exec_cmd} -b 1G -e 10G -i{increment} -n {iterations}"
        ]
    elif shape in ("BM.GPU.H100.8", "BM.GPU.H200.8", "BM.GPU.B200.8", "BM.GPU.RTXPRO.8") or (shape in ("BM.GPU.B300.8", "BM.GPU.B300.HS.8") and not multiplanar):
        mpirun_cmd = [
            "mpirun", "--mca", "pml", "ucx",
            "--bind-to", "numa",
            "--mca", "coll", "^hcoll",
            "--mca", "plm_rsh_no_tree_spawn", "1",
            "-x", "HCOLL_ENABLE_MCAST_ALL=0",
            "-x", "NCCL_CUMEM_ENABLE=0",
            "-x", "NCCL_IB_SPLIT_DATA_ON_QPS=0",
            "-x", "NCCL_IB_QPS_PER_CONNECTION=1",
            "-x", "NCCL_IB_GID_INDEX=3",
            "-x", "NCCL_IB_TC=41",
            "-x", "NCCL_IB_SL=0",
            "-x", "NCCL_IB_TIMEOUT=22",
            "-x", "NCCL_NET_PLUGIN=none",
            "-x", "coll_hcoll_enable=0",
            "-x", "UCX_TLS=tcp",
            "-x", f"UCX_NET_DEVICES={var_UCX_NET_DEVICES}",
            "-x", f"NCCL_IB_HCA={var_NCCL_IB_HCA}",
            "-x", "RX_QUEUE_LEN=8192",
            "-x", "IB_RX_QUEUE_LEN=8192",
            "-x", f"NCCL_SOCKET_IFNAME={var_UCX_NET_DEVICES}",
            "-x", "NCCL_IGNORE_CPU_AFFINITY=1",
            "-x", f"NCCL_DEBUG={NCCL_DEBUG}",
            "--np", "16",
            "--rankfile", hostfile,
            "bash","-c",
            f"{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n {iterations}"
        ]
    elif shape == "BM.GPU.GB200.4":
        for mnnvl_enable in get_gb_mnnvl_test_values(client_host, server_host):
            nccl_test_cases.append((
                f"NCCL MNNVL={mnnvl_enable}",
                [
                    "mpirun",
                    "--bind-to", "none",
                    "--mca", "coll", "^hcoll",
                    "--mca", "plm_rsh_no_tree_spawn", "1",
                    "-x", f"NCCL_MNNVL_ENABLE={mnnvl_enable}",
                    "-x", "NCCL_NET_PLUGIN=none",
                    "-x", "NCCL_NET_GDR_C2C=1",
                    "-x", "NCCL_NVLS_ENABLE=1",
                    "-x", f"UCX_NET_DEVICES={var_NCCL_IB_HCA}",
                    "-x", f"NCCL_IB_HCA={var_NCCL_IB_HCA}",
                    "-x", f"NCCL_SOCKET_IFNAME={var_UCX_NET_DEVICES}",
                    "-x", f"NCCL_DEBUG={NCCL_DEBUG}",
                    "--np", "8",
                    "--rankfile", hostfile,
                    "bash","-c",
                    f"{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n {iterations}"
                ],
                mnnvl_enable,
            ))
    elif multiplanar:
        if shape in ("BM.GPU.B300.8", "BM.GPU.B300.HS.8"):
            mnnvl_test_values = [None]
        else:
            mnnvl_test_values = get_gb_mnnvl_test_values(client_host, server_host)

        for mnnvl_enable in mnnvl_test_values:
            label = "NCCL RDMA-only" if mnnvl_enable is None else (
                "NCCL RDMA-only MNNVL=0" if mnnvl_enable == 0 else f"NCCL MNNVL={mnnvl_enable}"
            )
            mpirun_cmd = [
                "mpirun",
                "--bind-to", "numa",
                "--mca", "pml", "ucx",
                "--mca", "coll", "^hcoll",
                "-x", "LD_LIBRARY_PATH",
                "-x", f"UCX_NET_DEVICES={var_UCX_NET_DEVICES}",
                "-x", "RX_QUEUE_LEN=8192",
                "-x", "IB_RX_QUEUE_LEN=8192",
                "-x", "HCOLL_ENABLE_MCAST_ALL=0",
                "-x", "coll_hcoll_enable=0",
                "-x", f"NCCL_SOCKET_IFNAME={var_UCX_NET_DEVICES}",
                "-x", f"NCCL_IB_HCA={var_NCCL_IB_HCA}",
                "-x", "NCCL_ASYNC_ERROR_HANDLING=1",
                "-x", "NCCL_IB_TIMEOUT=16",
                "-x", "NCCL_IB_RETRY_CNT=7",
                "-x", "NCCL_IB_SL=0",
                "-x", "NCCL_IB_TC=96",
                "-x", "NCCL_IB_GID_INDEX=3",
                "-x", "NCCL_NVLS_ENABLE=1",
                "-x", "NCCL_WORK_FIFO_BYTES=0",
                "-x", "NCCL_NET_GDR_C2C=1",
                "-x", "NCCL_CUMEM_ENABLE=1",
                "-x", "NCCL_IGNORE_CPU_AFFINITY=1",
                "-x", "NCCL_NET_PLUGIN=spcx",
                "-x", "NCCL_NET=IB",
                "-x", "NCCL_IB_ADAPTIVE_ROUTING=1",
                "-x", "NCCL_IB_SPLIT_DATA_ON_QPS=0",
                "-x", "NCCL_IB_QPS_PER_CONNECTION=16",
            ]
            if mnnvl_enable is not None:
                mpirun_cmd.extend(["-x", f"NCCL_MNNVL_ENABLE={mnnvl_enable}"])
            if shape == "BM.GPU.GB300.4":
                mpirun_cmd.extend(["-x", f"NCCL_TOPO_FILE={GB300_MULTIPLANAR_NCCL_TOPO_FILE}"])
            elif shape == "BM.GPU.B300.8":
                mpirun_cmd.extend(["-x", f"NCCL_TOPO_FILE={B300_MULTIPLANAR_NCCL_TOPO_FILE}"])
            elif shape == "BM.GPU.B300.HS.8":
                mpirun_cmd.extend(["-x", f"NCCL_TOPO_FILE={B300_MULTIPLANAR_NCCL_TOPO_FILE}"])
            mpirun_cmd.extend([
                "-x", f"NCCL_DEBUG={NCCL_DEBUG}",
                "--np", "8",
                "--rankfile", hostfile,
                "bash","-c",
                f"{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n 50"
            ])
            nccl_test_cases.append((
                label,
                mpirun_cmd,
                mnnvl_enable,
            ))
    elif is_gb_shape(shape):
        for mnnvl_enable in get_gb_mnnvl_test_values(client_host, server_host):
            nccl_test_cases.append((
                f"NCCL MNNVL={mnnvl_enable}",
                [
                    "mpirun",
                    "--bind-to", "numa",
                    "--mca", "pml", "ucx",
                    "--mca", "coll", "^hcoll",
                    "-x", f"NCCL_MNNVL_ENABLE={mnnvl_enable}",
                    "-x", "NCCL_CUMEM_ENABLE=1",
                    "-x", "NCCL_NET_PLUGIN=none",
                    "-x", "NCCL_NET_GDR_C2C=1",
                    "-x", "NCCL_NVLS_ENABLE=1",
                    "-x", f"UCX_NET_DEVICES={var_UCX_NET_DEVICES}",
                    "-x", f"NCCL_IB_HCA={var_NCCL_IB_HCA}",
                    "-x", f"NCCL_SOCKET_IFNAME={var_UCX_NET_DEVICES}",
                    "-x", f"NCCL_DEBUG={NCCL_DEBUG}",
                    "-x", "NCCL_IB_GID_INDEX=3",
                    "-x", "NCCL_IB_TC=41",
                    "-x", "NCCL_IB_SL=0",
                    "-x", "NCCL_IB_TIMEOUT=22",
                    "-x", "RX_QUEUE_LEN=8192",
                    "-x", "IB_RX_QUEUE_LEN=8192",
                    "-x", "HCOLL_ENABLE_MCAST_ALL=0",
                    "-x", "coll_hcoll_enable=0",
                    "-x", "NCCL_IB_QPS_PER_CONNECTION=4",
                    "-x", "NCCL_IB_SPLIT_DATA_ON_QPS=0",
                    "-x", "NCCL_DMABUF_ENABLE=1",
                    "-x", "NCCL_NET_GDR_LEVEL=SYS",
                    "--np", "8",
                    "--rankfile", hostfile,
                    "bash","-c",
                    f"{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n 50"
                ],
                mnnvl_enable,
            ))
    else:
        return False,"NCCL Test Failed: No suitable shape found for NCCL test"

    if not nccl_test_cases:
        nccl_test_cases = [("NCCL", mpirun_cmd, None)]

    outputs = []
    for label, mpirun_cmd, mnnvl_enable in nccl_test_cases:
        test_state, test_output = run_nccl_test_case(
            mpivars_path,
            mpirun_cmd,
            shape,
            label,
            mnnvl_enable=mnnvl_enable,
        )
        if not test_state:
            return test_state, test_output
        outputs.append(test_output)
    return True, "; ".join(outputs)

def run_multi_node_rccl_test(hostfile, shape):

    paths = glob.glob('/usr/mpi/gcc/openmpi-*/bin/mpivars.sh')
    if paths:
        mpivars_path = paths[0]
    else:
        return False,"RCCL Test Failed: No mpivars.sh found"

    increment=1024*1024*1024*9
    NCCL_DEBUG="WARN"
    exec_cmd="/opt/rccl-tests/build/all_reduce_perf"

    var_UCX_NET_DEVICES = shape_mapping.get(shape, {}).get('var_UCX_NET_DEVICES', '')
    if var_UCX_NET_DEVICES == "":
        return False,"RCCL Test Failed: Shape not found for RCCL test"
    var_NCCL_IB_HCA = shape_mapping.get(shape, {}).get('var_NCCL_IB_HCA', '')
    if "BM.GPU.MI" in shape:
        mpirun_cmd = [
            "mpirun", "--mca", "pml", "ucx",
            "--bind-to", "numa",
            "--mca", "plm_rsh_no_tree_spawn", "1",
            "-x", f"UCX_NET_DEVICES={var_UCX_NET_DEVICES}",
            "-x", "NCCL_SOCKET_IFNAME=eth0",
            "-x", "NCCL_IB_SL=0",
            "-x", f"NCCL_IB_HCA={var_NCCL_IB_HCA}",
            "-x", "coll_hcoll_enable=0",
            "-x", "HCOLL_ENABLE_MCAST_ALL=0",
            "-x", "NCCL_IGNORE_CPU_AFFINITY=1",
            "-x", "NCCL_IB_QPS_PER_CONNECTION=4",
            "-x", "RX_QUEUE_LEN=8192",
            "-x", "IB_RX_QUEUE_LEN=8192",
            "--np", "16",
            "--hostfile", hostfile,
            "bash","-c",
            f"sleep $((RANDOM % 5));{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n 50"
        ]

    else:
        return False,"RCCL Test Failed: No suitable shape found for RCCL test"

    # Prepare the mpirun command as a string with proper quotations
    mpirun_str = custom_join(mpirun_cmd)
    cmd = f"source {mpivars_path} && {mpirun_str}"


    i = 0
    while i < 5:
        logger.info(f"NCCL Test {i+1}/5")
        i += 1
        try:
            result = subprocess.run(
                cmd,
                text=True,
                timeout=120,
                shell=True,
                executable='/bin/bash',  # Needed to use 'source mpivars.sh'
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            if result.returncode == 0:
                output = result.stdout
                bw=None
                threshold = shape_mapping.get(shape, {}).get("threshold")
                if threshold == "":
                    return False,"RCCL Test Failed: Shape not found for RCCL test"
                for line in output.splitlines():
                    if "Avg bus bandwidth" in line:
                        try:
                            bw=float(line.split()[5])
                        except:
                            if i < 4:
                                continue
                            return False,"RCCL Test Failed: Avg bus bandwidth could not be found"
                        if bw < threshold:
                            if i < 4:
                                continue
                            return False,f"RCCL Test Failed: Avg bus bandwidth is {bw} which is less than {threshold}"
                if bw is not None:
                    return True,"RCCL Test Succeeded: Avg bus bandwidth is " + str(bw)
                else:
                    if i < 4:
                        continue
                    return False,"RCCL Test Failed: Avg bus bandwidth could not be found"
            else:
                if i < 4:
                    continue
                logger.error(f"Multi-node RCCL Test Failed: Failed to run multi-node nccl test. {result.stderr}")
                logger.info(f"result: {potentially_bad}")
                return False,f"Multi-node RCCL Test Failed: Failed to run multi-node nccl test. {result.stderr}"
        except subprocess.TimeoutExpired:
            if i < 4:
                continue
            return False,"RCCL Test Failed: NCCL test timed out after 2 minutes"
        except Exception as e:
            if i < 4:
                continue
            return False, f"RCCL Test Failed: Failed to run nccl test. {e}"


def _parse_ib_write_bw_value(output):
    for line in output.splitlines():
        parts = line.split()
        if not parts or parts[0] != "65536":
            continue
        for idx in (3, 2):
            if len(parts) > idx:
                try:
                    return float(parts[idx])
                except ValueError:
                    continue
    return None


def run_ib_write_bw(shape, server, client='localhost'):
    ib_write_bw = shape_mapping.get(shape, {}).get('ib_write_bw', '')
    if ib_write_bw == "":
        return False,"ib write bw Test Failed: Shape not found for ib write test"

    var_NCCL_IB_HCA = shape_mapping.get(shape, {}).get('var_NCCL_IB_HCA', '')
    hca_list = [dev for dev in var_NCCL_IB_HCA.lstrip("=").split(',') if dev]
    if not hca_list:
        return False,"ib write bw Test Failed: No RDMA devices found for ib write test"

    cmd_base = "/usr/bin/ib_write_bw -F -q 2 -x 3 --report_gbits -D 10"
    threshold = float(ib_write_bw)
    last_error = ""
    for i in range(3):
        results = {}
        errors = {}
        logger.info(f"ib write bw Test {i+1}/3")
        for dev in hca_list:
            cmd = get_multiplanar_ib_command(
                cmd_base,
                dev,
                shape=shape,
                use_cuda=is_multiplanar_rdma_vf_device(dev),
            )
            server_cmd = cmd
            client_cmd = f"{cmd} {shlex.quote(server)}"

            if is_multiplanar_rdma_vf_device(dev):
                server_ipv6 = get_ipv6_for_ib_device(server, dev)
                if not server_ipv6:
                    results[dev] = None
                    errors[dev] = "could not find global IPv6 address"
                    logger.warning(f"{server} {dev}: could not find global IPv6 address")
                    continue
                server_cmd = f"{cmd} --ipv6-addr"
                client_cmd = f"{cmd} --ipv6-addr {shlex.quote(server_ipv6)}"

            server_proc = subprocess.Popen(
                ["ssh", server, f"exec {server_cmd}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                time.sleep(1)
                client_output = subprocess.check_output(
                    ["ssh", client, client_cmd],
                    timeout=60,
                    text=True,
                    stderr=subprocess.STDOUT,
                )
                bw = _parse_ib_write_bw_value(client_output)
                results[dev] = bw
                if bw is None:
                    errors[dev] = "could not parse bandwidth"
                    logger.warning(f"ib write bw: could not parse bandwidth for {dev}: {client_output.strip()}")
            except subprocess.CalledProcessError as e:
                results[dev] = None
                errors[dev] = str(e)
                logger.warning(f"ib write bw: failed for {dev}: {e}")
            except subprocess.TimeoutExpired:
                results[dev] = None
                errors[dev] = "timeout after 60 seconds"
                logger.warning(f"ib write bw: timeout after 60 seconds for {dev}")
            finally:
                server_proc.terminate()
                try:
                    server_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server_proc.kill()

        numeric_results = {dev: value for dev, value in results.items() if value is not None}
        if numeric_results:
            avg_bw = sum(numeric_results.values()) / len(numeric_results)
            per_interface = ", ".join(
                f"{dev}={value:.2f}" for dev, value in sorted(numeric_results.items())
            )
            logger.info(
                f"ib write bw average bandwidth is {avg_bw:.2f} Gb/s "
                f"(threshold: {threshold:g} Gb/s); per-interface: {per_interface}"
            )

        error_dict = {dev: value for dev, value in results.items() if value is None or value < threshold}
        if not error_dict:
            threshold_text = f"{threshold:g}"
            return True,"ib write bw Test Succeeded: Bandwidth for each RDMA interface is equal to or above the threshold of " + threshold_text + " Gb/s"

        pairs = []
        for dev, value in sorted(error_dict.items()):
            if value is None:
                pairs.append(f"{dev} ({errors.get(dev, 'no bandwidth result')})")
            else:
                pairs.append(f"{dev} ({value})")
        interfaces_str = ' and '.join(pairs)
        last_error = f"WARNING: BW was below the threshold {threshold:g} Gb/s for interface {interfaces_str}"
        logger.warning(last_error)

    if last_error:
        return False, last_error
    return False,"ib write bw Test Failed: Bandwidth is less than the threshold of " + str(ib_write_bw) + " Gb/s for one or more RDMA interfaces"

def run_ib_write_lat(shape, server, client='localhost'):
    ib_write_lat_threshold = shape_mapping.get(shape, {}).get('ib_write_lat', '')
    if ib_write_lat_threshold == "":
        return False,"ib write latency Test Failed: Shape not found for ib write latency test"
    # Helper to execute ssh command and return stdout
    def ssh(host, cmd):
        try:
            result = subprocess.run(
                ['ssh', host, cmd],
                timeout=60,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                check=True  # ensures CalledProcessError is raised on error
            )
            return True, result.stdout  # Return success and output string
        except subprocess.CalledProcessError as e:
            return False, f"ib write latency Test Failed: Failed to run ib write latency test (exit code {e.returncode}): {e}"
        except subprocess.TimeoutExpired as e:
            return False, "ib write latency Test Failed: Timed out after 60 seconds"

    var_NCCL_IB_HCA = shape_mapping.get(shape, {}).get('var_NCCL_IB_HCA', '')
    hca_list = var_NCCL_IB_HCA.lstrip('=').split(',')
    total_hcas = len(hca_list)
    half = total_hcas // 2
    cmd_base = "/usr/bin/ib_write_lat -F -x 3 -s 8 -n 10000"

    for i in range(3):
        success = True
        error_dict = {}
        logger.info(f"ib write lat  Test {i+1}/3")
        for idx, dev in enumerate(hca_list):
            numa_node = 0 if idx < half else 1
            if is_multiplanar_rdma_vf_device(dev):
                cmd = get_multiplanar_ib_command(cmd_base, dev)
                server_ipv6 = get_ipv6_for_ib_device(server, dev)
                if not server_ipv6:
                    error_dict[dev] = None
                    success = False
                    logger.warning(f"{server} {dev}: could not find global IPv6 address")
                    continue
                server_cmd = f"nohup {cmd} --ipv6-addr > /dev/null 2>&1 &"
                client_cmd = (
                    f"{cmd} --ipv6-addr {shlex.quote(server_ipv6)} | "
                    "grep '^ 8[[:space:]]\\+10000' | awk '{print $6}'"
                )
            else:
                # Start server side as background process (no output)
                # Use 'nohup' to not kill process if ssh disconnects
                server_cmd = f"nohup numactl -N {numa_node} {cmd_base} -d {dev} > /dev/null 2>&1 &"
                client_cmd = (
                    f"numactl -N {numa_node} {cmd_base} -d {dev} {shlex.quote(server)} | "
                    "grep '^ 8[[:space:]]\\+10000' | awk '{print $6}'"
                )

            cmd_state,cmd_output = ssh(server, server_cmd)
            if not cmd_state:
                return cmd_state,cmd_output

            time.sleep(1)  # Give server time to listen

            cmd_state,cmd_output = ssh(client, client_cmd)
            if not cmd_state:
                return cmd_state,cmd_output
            latency = cmd_output.strip()
            if latency != "":
                latency = float(latency)
                if latency > ib_write_lat_threshold:
                    error_dict[dev] = latency
                    success = False
            else:
                error_dict[dev] = None
                success = False
        if success:
            return True,"ib write latency Test Succeeded: Latency for each RDMA interface is less than the threshold of " + str(ib_write_lat_threshold) + " microseconds"
        else:
            if i < 2:
                continue
            # Create a string for each key-value pair
            pairs = [f"{key} ({value})" for key, value in error_dict.items()]
            # Join them with ' and '
            interfaces_str = ' and '.join(pairs)
            # Construct the full message
            msg = f"WARNING: Latency was greater than the threshold {ib_write_lat_threshold} for interface {interfaces_str}"
            logger.warning(msg)
            return False,"ib write latency Test Failed: Latency is equal to or above the threshold of " + str(ib_write_lat_threshold) + " microseconds for one or more RDMA interfaces"

def write_hc_http_server_file(node1, node2):
    slurm_error = False

    http_server_file="/opt/oci-hpc/http_server/files/healthchecks"
    # Read the existing data from the file
    try:
        with open(http_server_file, 'r') as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.debug(f"{hostname}: Error: File not found or not in valid JSON format.")
        data={}

    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    data["multi_node_healthcheck_time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")

    prev_multi_node_hc_status = data.get("multi_node_healthcheck_status")
    prev_multi_node_hc_assoc_node = data.get("multi_node_healthcheck_associated_node")

    if os.uname().nodename.split(".", 1)[0] == node1.split(".", 1)[0]:
        multi_node_HC_associated_node = node2
    else:
        multi_node_HC_associated_node = node1
    data["multi_node_healthcheck_associated_node"] = multi_node_HC_associated_node

    healthcheck = healthy
    # Read the latest_multi_node_active_healthcheck.log file content

    try:
        with open("/var/log/healthchecks/latest_multi_node_active_healthcheck.log", 'r') as log_file:
            raw_content = log_file.read()
            content = raw_content
            # Limit log content to 2048 characters, keeping start and end
            if len(content) > 4096:
                half = 2000  # Half of 2048 to keep from start and end
                content = content[:half] + "\n... [truncated] ...\n" + content[-half:]
            data["multi_node_healthcheck_logs"] = content  # Store log content in JSON

            # Check for errors in the full log content
            for line in raw_content.splitlines():
                if "ERROR" in line:
                    healthcheck = potentially_bad
            logger.info(f"{hostname} - Multi-node Healthcheck Result: {healthcheck}")
    except FileNotFoundError:
        logger.warning(f"{hostname}: Log file not found, initializing empty logs.")
        data["multi_node_healthcheck_logs"] = ""

    if healthcheck == healthy:
        data["multi_node_healthcheck_status"] = healthy
        data["multi_node_healthcheck_recommendation"] = healthy
    elif healthcheck == potentially_bad and (prev_multi_node_hc_status == potentially_bad or prev_multi_node_hc_status == bad) and prev_multi_node_hc_assoc_node != multi_node_HC_associated_node:
        data["multi_node_healthcheck_status"] = bad
        data["multi_node_healthcheck_recommendation"] = "Tag and Terminate"
        slurm_error = True
    else:
        data["multi_node_healthcheck_status"] = potentially_bad
        data["multi_node_healthcheck_recommendation"] = "Run the multi-node active healthcheck with another node"
    logger.info(f"{hostname} - Data to write: {data}")
    # Write updated data back to the file
    with open(http_server_file, 'w') as file:
        try:
            json.dump(data, file, indent=4)
        except Exception as e:
            logger.error(f"Error writing to file: {e}")

    slurm_reason = "Healthcheck, multi-node active healthcheck test failed"
    if slurm_error and args.slurm:
        logger.info(f"{hostname}: Healthcheck_Multi:: {slurm_reason}")
        logger.info(f"{hostname}: Healthcheck_Multi:: Recommended Action: Tag and Terminate")
        cmd = [
            'sudo', 'scontrol', 'update',
            f'nodename={hostname}',
            'state=drain',
            f'reason={slurm_reason}'
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=20)
        except subprocess.CalledProcessError as e:
            logger.error(f"{hostname}: Node Drain Error: {e.stderr}")
        except subprocess.TimeoutExpired:
            logger.error(f"{hostname}: Node Drain Error. Drain command timed out after 20 seconds.")

if __name__ == '__main__':
    action = None
    parser = argparse.ArgumentParser(description='Multi-node active healthchecks')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('-m', '--mode', required=True, type=int, choices=[1,2,3], help='1: write node details, 2: run multi-node active healthchecks, 3: write to /opt/oci-hpc/http_server/files/healthchecks')
    parser.add_argument('-f', '--hostfile', type=str, help='Hostfile with one host per line')
    parser.add_argument('-n', '--node1', type=str, help='node1 name')
    parser.add_argument('-o', '--node2', type=str, help='node2 name')
    parser.add_argument('-slurm', '--slurm', action='store_true', help='Add a Slurm message')

    args = parser.parse_args()
    metadata = get_metadata()
    shape = metadata['shape']
    hostname = metadata['displayName']
    ocid = metadata['id']
    logger.setLevel(args.log_level)
    apply_shape_overrides(shape)
    var_NCCL_IB_HCA = shape_mapping.get(shape, {}).get('var_NCCL_IB_HCA', '')
    if var_NCCL_IB_HCA == "":
        logger.error("Shape not found for multi-node active healthcheck")
        sys.exit(1)

    if args.mode == 1:
        get_node_details()
    elif args.mode == 2:
        if not args.hostfile.strip():
            logger.error("Error: --hostfile argument cannot be empty", flush=True)
            sys.exit(1)
        nodes=[]
        with open(args.hostfile, 'r') as f:
            for line in f:
                node=line.split('=')[1].split()[0]
                if node not in nodes:
                    nodes.append(node)
        client_host, server_host = nodes

        file_handler = logging.FileHandler("/var/log/healthchecks/latest_multi_node_active_healthcheck.log", mode='w')
        logger.addHandler(file_handler)

        datetime_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Started multi-node active healthcheck at: {datetime_str}")

        if "BM.GPU.MI" not in shape:
            nccl_state,nccl_output = run_multi_node_nccl_test(args.hostfile, shape, client_host, server_host)
            if not nccl_state:
                logger.error(nccl_output)
            else:
                logger.info(nccl_output)
        else:
            rccl_state,rccl_output = run_multi_node_rccl_test(args.hostfile, shape)
            if not rccl_state:
                logger.error(rccl_output)
            else:
                logger.info(rccl_output)

        ib_write_bw_state,ib_write_bw_output = run_ib_write_bw(shape, server_host, client_host)
        if not ib_write_bw_state:
            logger.error(ib_write_bw_output)
        else:
            logger.info(ib_write_bw_output)

        ib_write_lat_state,ib_write_lat_output = run_ib_write_lat(shape, server_host, client_host)
        if not ib_write_lat_state:
            logger.error(ib_write_lat_output)
        else:
            logger.info(ib_write_lat_output)

        datetime_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        logger.info(f"Finished multi-node active healthcheck at: {datetime_str}")
    elif args.mode == 3:
        if not args.node1.strip():
            logger.error("Error: --node1 argument cannot be empty", flush=True)
            sys.exit(1)
        if not args.node2.strip():
            logger.error("Error: --node2 argument cannot be empty", flush=True)
            sys.exit(1)
        write_hc_http_server_file(args.node1, args.node2)
