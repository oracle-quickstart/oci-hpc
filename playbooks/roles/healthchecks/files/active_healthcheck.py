#!/usr/bin/env python3
import sys
import os
import argparse
import json
import requests
import yaml
import subprocess
import logging
import getpass
import time
import stat
import tempfile
import glob
import re
import shlex

MULTIPLANAR_RDMA_VF_COUNTS = {
    "BM.GPU.B300.8": 8,
    "BM.GPU.B300.HS.8": 8,
    "BM.GPU.GB300.4": 4,
}

B300_MULTIPLANAR_NCCL_TOPO_FILE = "/opt/oci-hpc/healthchecks/B300MP.xml"

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
        and get_rdma_planes() > 1
    )

def is_b300_multiplanar(shape):
    return (
        shape in ("BM.GPU.B300.8", "BM.GPU.B300.HS.8")
        and get_rdma_planes() > 1
    )

# Check if the user is root
def is_user_root():
    if os.geteuid() != 0:
        logger.debug("User is not root!")
        return False
    return True

def get_default_user():
    try:
        with open("/etc/os-release") as f:
            data = f.read().lower()

        if any(word in data for word in ["ubuntu", "debian"]):
            return "ubuntu"

        if any(word in data for word in ["oracle", "rhel", "centos", "rocky", "alma", "fedora"]):
            return "opc"

        return "root"  # fallback if unknown
    except FileNotFoundError:
        return "root"

def is_user_default():
    default_user = get_default_user()
    if getpass.getuser() != default_user:
        return False,default_user
    return True,default_user

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

def run_as_default_user(cmd, timeout=None):
    user_is_default,default_user = is_user_default()
    if user_is_default:
        cmd_user = ["bash", "-lc", cmd]
    else:
        cmd_user = ["sudo", "-u", default_user, "-i", "bash", "-lc", cmd]

    return subprocess.run(cmd_user, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)

def run_local_nccl_test(shape):
    # Set defaults
    shape_mapping = {
        "BM.GPU.B4.8": {
            "var_NCCL_IB_HCA": "=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12",
            "threshold": 185,
        },
        "BM.GPU.A100-v2.8": {
            "var_NCCL_IB_HCA": "=mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_14,mlx5_15,mlx5_16,mlx5_17,mlx5_9,mlx5_10,mlx5_11,mlx5_12",
            "threshold": 185,
        },
        "BM.GPU4.8": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_2,mlx5_6,mlx5_8,mlx5_10,mlx5_12,mlx5_14,mlx5_16,mlx5_1,mlx5_3,mlx5_7,mlx5_9,mlx5_11,mlx5_13,mlx5_15,mlx5_17",
            "threshold": 185,
        },
        "BM.GPU.H100.8": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_12,mlx5_13,mlx5_14,mlx5_15,mlx5_16,mlx5_17",
            "threshold": 440,
        },
        "BM.GPU.H200.8": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11",
            "threshold": 440,
        },
        "BM.GPU.B200.8": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_9,mlx5_10,mlx5_11",
            "threshold": 440,
        },
        "BM.GPU.B300.8": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_11,mlx5_12,mlx5_13,mlx5_14,mlx5_16,mlx5_17,mlx5_18,mlx5_19,mlx5_20,mlx5_21",
            "threshold": 800,
        },
        "BM.GPU.B300.HS.8": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_7,mlx5_8,mlx5_9,mlx5_10,mlx5_11,mlx5_12,mlx5_13,mlx5_14,mlx5_16,mlx5_17,mlx5_18,mlx5_19,mlx5_20,mlx5_21",
            "threshold": 800,
        },
        "BM.GPU.RTXPRO.8": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_6,mlx5_7,mlx5_8,mlx5_9",
            "threshold": 25,
        },
        "BM.GPU.GB200.4": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_3,mlx5_4",
        },
        "BM.GPU.GB200-v2.4": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_3,mlx5_4",
        },
        "BM.GPU.GB200-v3.4": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8",
        },
        "BM.GPU.GB300.4": {
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8",
            "threshold": 660,
        },
        "BM.Optimized3.36": {
            "var_NCCL_IB_HCA": "=mlx5_2",
        },
        "BM.GPU.MI300X.8": {
            "var_UCX_NET_DEVICES": "mlx5_0:1",
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_7,mlx5_8,mlx5_9",
            "threshold": 350
        }  ,
        "BM.GPU.MI355X.8": {
            "var_UCX_NET_DEVICES": "mlx5_8:1",
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7",
            "threshold": 350
        }    ,
        "BM.GPU.MI355X-v0.8": {
            "var_UCX_NET_DEVICES": "mlx5_8:1",
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7",
            "threshold": 350
        }    ,
        "BM.GPU.MI355X-v1.8": {
            "var_UCX_NET_DEVICES": "mlx5_8:1",
            "var_NCCL_IB_HCA": "=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7",
            "threshold": 350
        }    
    }

    b300_multiplanar = is_b300_multiplanar(shape)
    gb300_multiplanar = is_gb300_multiplanar(shape)
    if b300_multiplanar:
        rdma_vf_devices = discover_multiplanar_rdma_devices(shape)
        shape_mapping[shape].update({
            "var_NCCL_IB_HCA": ",".join(rdma_vf_devices),
        })
        logger.info(f"Using B300 MultiPlanar RDMA VF devices: {rdma_vf_devices}")

    if gb300_multiplanar:
        rdma_vf_devices = discover_multiplanar_rdma_devices(shape)
        shape_mapping[shape].update({
            "var_NCCL_IB_HCA": ",".join(rdma_vf_devices),
        })
        logger.info(f"Using GB300 MultiPlanar RDMA VF devices: {rdma_vf_devices}")

    try:
        with open("/etc/manifest.yaml") as manifest_file:
            version = yaml.safe_load(manifest_file)["verified_components"]["openmpi"]["version"]
        if isinstance(version, str) and version.startswith("v"):
            version = version[1:]
        if not isinstance(version, str) or not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]*", version):
            raise ValueError("invalid Open MPI version")
        mpirun_path = f"/opt/openmpi-{version}/bin/mpirun"
        if not os.access(mpirun_path, os.X_OK):
            raise ValueError(f"launcher is not executable: {mpirun_path}")
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as e:
        return False, f"NCCL Test Failed: cannot select image MPI from /etc/manifest.yaml: {e}"
    plugin_args = ""
    plugin = "none"
    plugin_pattern = None
    if b300_multiplanar or gb300_multiplanar:
        plugin_pattern = '/opt/hpcx-*/nccl_spectrum-x_plugin/lib/libnccl-net-spcx.so'
    elif shape in ("BM.GPU.GB200.4", "BM.GPU.GB200-v2.4", "BM.GPU.GB200-v3.4", "BM.GPU.GB300.4"):
        plugin_pattern = '/opt/hpcx-*/nccl_rdma_sharp_plugin/lib/libnccl-net.so'
    if plugin_pattern:
        plugins = glob.glob(plugin_pattern)
        if len(plugins) != 1:
            return False, f"NCCL Test Failed: expected one network plugin matching {plugin_pattern}"
        plugin = shlex.quote(plugins[0])
        plugin_dir = shlex.quote(os.path.dirname(plugins[0]))
        plugin_args = f"-x LD_LIBRARY_PATH={plugin_dir}"

    # MPI coordinates ranks; NCCL owns GPU/RDMA communication.
    mpirun_prefix = " ".join([shlex.quote(mpirun_path),
                              "--mca pml ob1",
                              "--mca btl self,sm,tcp",
                              "--mca btl_tcp_if_include eth0",
                              "--mca coll ^ucc,hcoll",
                              f"-x NCCL_NET_PLUGIN={plugin}",
                              "-x NCCL_SOCKET_IFNAME=eth0",
                              plugin_args

        ])
    if shape in ("BM.GPU.B4.8", "BM.GPU.A100-v2.8", "BM.GPU4.8"):
        cmd_nccl_test=f"""
            {mpirun_prefix} \
                --bind-to numa \
                --mca plm_rsh_no_tree_spawn 1 \
                -x NCCL_ALGO=Ring \
                -x NCCL_DEBUG=WARN \
                -x NCCL_IB_GID_INDEX=3 \
                -x NCCL_IB_HCA={shape_mapping[shape]['var_NCCL_IB_HCA']} \
                -x NCCL_IB_QPS_PER_CONNECTION=4 \
                -x NCCL_IB_SL=0 \
                -x NCCL_IB_TC=41 \
                --np 8 \
                /opt/oci-hpc/nccl-tests/bin/all_reduce_perf -b 1G -e 10G -g 1 -n 50 -f 2"""
    elif b300_multiplanar:
        cmd_nccl_test=f"""
            {mpirun_prefix} \
                --bind-to numa \
                --mca plm_rsh_no_tree_spawn 1 \
                -x NCCL_CUMEM_ENABLE=0 \
                -x NCCL_DEBUG=WARN \
                -x NCCL_IB_GID_INDEX=3 \
                -x NCCL_IB_HCA={shape_mapping[shape]['var_NCCL_IB_HCA']} \
                -x NCCL_IB_QPS_PER_CONNECTION=4 \
                -x NCCL_IB_ADAPTIVE_ROUTING=1 \
                -x NCCL_IB_SL=0 \
                -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
                -x NCCL_IB_TC=41 \
                -x NCCL_IB_TIMEOUT=22 \
                -x NCCL_IGNORE_CPU_AFFINITY=1 \
                -x NCCL_TOPO_FILE={B300_MULTIPLANAR_NCCL_TOPO_FILE} \
                -np 8 \
                /opt/oci-hpc/nccl-tests/bin/all_reduce_perf -b 1G -e 16G -g 1 -n 50 -f 2"""
    elif shape in ("BM.GPU.H100.8", "BM.GPU.H200.8", "BM.GPU.B200.8", "BM.GPU.B300.8", "BM.GPU.B300.HS.8", "BM.GPU.RTXPRO.8"):
        cmd_nccl_test=f"""
            {mpirun_prefix} \
                --bind-to numa \
                --mca plm_rsh_no_tree_spawn 1 \
                -x NCCL_CUMEM_ENABLE=0 \
                -x NCCL_DEBUG=WARN \
                -x NCCL_IB_GID_INDEX=3 \
                -x NCCL_IB_HCA={shape_mapping[shape]['var_NCCL_IB_HCA']} \
                -x NCCL_IB_QPS_PER_CONNECTION=1 \
                -x NCCL_IB_SL=0 \
                -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
                -x NCCL_IB_TC=41 \
                -x NCCL_IB_TIMEOUT=22 \
                -x NCCL_IGNORE_CPU_AFFINITY=1 \
                -np 8 \
                /opt/oci-hpc/nccl-tests/bin/all_reduce_perf -b 1G -e 16G -g 1 -n 50 -f 2"""
    elif gb300_multiplanar:
        cmd_nccl_test=f"""
            {mpirun_prefix} \
                --bind-to numa \
                --mca plm_rsh_no_tree_spawn 1 \
                -x NCCL_ASYNC_ERROR_HANDLING=1 \
                -x NCCL_CUMEM_ENABLE=1 \
                -x NCCL_DEBUG=WARN \
                -x NCCL_IB_ADAPTIVE_ROUTING=1 \
                -x NCCL_IB_GID_INDEX=3 \
                -x NCCL_IB_HCA={shape_mapping[shape]['var_NCCL_IB_HCA']} \
                -x NCCL_IB_RETRY_CNT=7 \
                -x NCCL_IB_SL=0 \
                -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
                -x NCCL_IB_QPS_PER_CONNECTION=16 \
                -x NCCL_IB_TC=96 \
                -x NCCL_IB_TIMEOUT=16 \
                -x NCCL_IGNORE_CPU_AFFINITY=1 \
                -x NCCL_MNNVL_ENABLE=1 \
                -x NCCL_NET_GDR_C2C=1 \
                -x NCCL_NVLS_ENABLE=1 \
                -x NCCL_WORK_FIFO_BYTES=0 \
                -x NCCL_TOPO_FILE=/opt/oci-hpc/healthchecks/GB300MP.xml \
                -np 4 \
                /opt/oci-hpc/nccl-tests/bin/all_reduce_perf -b 1G -e 16G -g 1 -n 50 -f 2"""
    elif "GPU.GB" in shape:
        # GB200/v2 use InfiniBand; v3 and GB300 SP use the RoCE benchmark defaults.
        qps = 1
        roce_args = ""
        if shape in ("BM.GPU.GB200-v3.4", "BM.GPU.GB300.4"):
            qps = 4
            roce_args = (
                "-x NCCL_IB_GID_INDEX=3 -x NCCL_IB_TC=41 -x NCCL_IB_SL=0 "
                "-x NCCL_IB_TIMEOUT=22 -x NCCL_BUFFSIZE=16777216 "
                "-x NCCL_IB_SPLIT_DATA_ON_QPS=0 "
                "-x NCCL_DMABUF_ENABLE=1"
            )
        cmd_nccl_test=f"""
            {mpirun_prefix} \
                --bind-to none \
                --mca plm_rsh_no_tree_spawn 1 \
                -x NCCL_IB_HCA={shape_mapping[shape]['var_NCCL_IB_HCA']} \
                -x NCCL_IB_QPS_PER_CONNECTION={qps} \
                -x NCCL_DEBUG=WARN \
                -x NCCL_MNNVL_ENABLE=1 \
                -x NCCL_CUMEM_ENABLE=1 \
                -x NCCL_NVLS_ENABLE=1 \
                -x NCCL_NET_GDR_C2C=1 \
                {roce_args} \
                -np 4 \
                /opt/oci-hpc/nccl-tests/bin/all_reduce_perf -b 1G -e 16G -g 1 -n 50 -f 2"""
    else:
        return False, f"NCCL Test Failed: unsupported shape {shape}"

    cmd_nccl_test = cmd_nccl_test.strip()

    threshold = shape_mapping.get(shape, {}).get("threshold", 0)
    last_error = "NCCL Test Failed"
    for attempt in range(1, 4):
        result = None
        logger.info(f"Starting NCCL test attempt {attempt}/3")
        try:
            result = run_as_default_user(cmd_nccl_test, timeout=120)
            if result.returncode != 0:
                output = result.stdout.decode('utf-8') if result.stdout else ""
                if not output and result.stderr:
                    output = result.stderr.decode('utf-8')
                last_error = output or f"NCCL command exited with return code {result.returncode}"
                logger.error(f"Failed to run local nccl test attempt {attempt}/3: {last_error}")
                continue

            output = result.stdout.decode('utf-8') if result.stdout else ""
            bw = None
            parse_failed = False
            for line in output.splitlines():
                if "Avg bus bandwidth" not in line:
                    continue
                try:
                    bw = float(line.split()[5])
                except (IndexError, ValueError):
                    parse_failed = True
                    last_error = "NCCL Test Failed: Avg bus bandwidth could not be parsed"
                    logger.error(f"{last_error} on attempt {attempt}/3")
                    break

            if bw is None:
                if not parse_failed:
                    last_error = "NCCL Test Failed: Avg bus bandwidth could not be found"
                    logger.error(f"{last_error} on attempt {attempt}/3")
                continue
            if bw < threshold:
                last_error = f"NCCL Test Failed: Avg bus bandwidth is less than {threshold}"
                logger.error(f"NCCL Test Failed on attempt {attempt}/3: Avg bus bandwidth is {bw}")
                continue

            if attempt > 1:
                logger.info(f"NCCL test succeeded on attempt {attempt}/3")
            return True, "NCCL Test Succeeded: Avg bus bandwidth is " + str(bw)
        except subprocess.TimeoutExpired:
            last_error = "Timeout after 2 minutes"
            logger.error(f"NCCL test attempt {attempt}/3 timed out after 2 minutes")
            if result and result.stdout:
                out = result.stdout.decode('utf-8')
                logger.error('\n'.join(out.splitlines()[-20:]))
        except Exception as e:
            last_error = str(e)
            logger.error(f"Failed to run local nccl test attempt {attempt}/3: {e}")
            if result and result.stdout:
                out = result.stdout.decode('utf-8')
                logger.error('\n'.join(out.splitlines()[-20:]))

    return False, f"NCCL Test Failed after 3 attempts: {last_error}"

    
def run_local_rccl_test(shape):
    shape_mapping = {
        "BM.GPU.MI300X.8": {"threshold": 310},
        "BM.GPU.MI355X.8": {"threshold": 310},
        "BM.GPU.MI355X-v0.8": {"threshold": 310},
        "BM.GPU.MI355X-v1.8": {"threshold": 310}
    }

    try:
        with open("/etc/manifest.yaml") as manifest_file:
            version = yaml.safe_load(manifest_file)["verified_components"]["openmpi"]["version"]
        if isinstance(version, str) and version.startswith("v"):
            version = version[1:]
        if not isinstance(version, str) or not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]*", version):
            raise ValueError("invalid Open MPI version")
        mpirun_path = f"/opt/openmpi-{version}/bin/mpirun"
        if not os.access(mpirun_path, os.X_OK):
            raise ValueError(f"launcher is not executable: {mpirun_path}")
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as e:
        return False, f"RCCL Test Failed: cannot select image MPI from /etc/manifest.yaml: {e}"

    result = None  # ensure defined
    try:
        cmd_gpu_count = "rocm-smi --showproductname --json | jq 'length'"
        gpu_count_proc = run_as_default_user(cmd_gpu_count)

        gpu_count_output = gpu_count_proc.stdout.decode('utf-8').strip().split('\n')[-1] if gpu_count_proc.stdout else ""
        if not gpu_count_output:
            logger.error("rocm-smi returned no output; cannot detect GPU count")
            return False, "rocm-smi returned no output; RCCL test skipped"

        try:
            gpu_count = int(gpu_count_output.split()[0])
        except Exception:
            logger.error(f"Could not parse GPU count from: {gpu_count_output}")
            return False, f"Could not parse GPU count from: {gpu_count_output}"

        # Use the selected image MPI libraries as well as its launcher.
        cmd_rccl_test = (
            f"source {shlex.quote(f'/opt/openmpi-{version}/bin/mpivars.sh')} && "
            f"{shlex.quote(mpirun_path)} --bind-to none --np 1 "
            f"/opt/rccl-tests/build/all_reduce_perf -b 1G -e 16G -g {gpu_count} -n 50 -f 2"
        )
        result = run_as_default_user(cmd_rccl_test, timeout=120)

        if result.returncode == 0:
            output = result.stdout.decode('utf-8') if result.stdout else ""
            bw = None
            for line in output.splitlines():
                if "Avg bus bandwidth" in line:
                    try:
                        bw = float(line.split()[5])
                    except Exception:
                        logger.error("RCCL Test Failed: Avg bus bandwidth could not be parsed")
                        return False, "RCCL Test Failed: Avg bus bandwidth parse error"
                    if bw < shape_mapping.get(shape, {}).get("threshold", 0):
                        logger.error(f"RCCL Test Failed: Avg bus bandwidth is {bw}")
                        return False, f"RCCL Test Failed: below threshold {shape_mapping[shape]['threshold']}"
            if bw is not None:
                return True, f"RCCL Test Succeeded: Avg bus bandwidth is {bw}"
            else:
                logger.error("RCCL Test Failed: Avg bus bandwidth not found in output")
                return False, "RCCL Test Failed: no bandwidth found"
        else:
            output = result.stdout.decode('utf-8') if result.stdout else result.stderr.decode('utf-8')
            logger.error(f"Failed to run local RCCL test: {output}")
            return False, output

    except subprocess.TimeoutExpired:
        logger.error("RCCL test timed out after 2 minutes")
        if result and result.stdout:
            logger.error('\n'.join(result.stdout.decode('utf-8').splitlines()[-20:]))
        return False, "Timeout after 2 minutes"
    except Exception as e:
        logger.error(f"Failed to run local RCCL test: {e}")
        if result and result.stdout:
            logger.error('\n'.join(result.stdout.decode('utf-8').splitlines()[-20:]))
        return False, str(e)

def run_gpu_fryer(run_time):
    command_run_time = run_time
    image_prepare_timeout = 1800
    container_run_timeout = command_run_time + 240
    gpu_fryer_image = "ghcr.io/huggingface/gpu-fryer:1.1.0"
    gpu_fryer_tar = "/config/3rdparty/docker/gpu-fryer-1.1.0.tar"
    gpu_fryer_pull_failed_marker = "GPU Fryer image pull failed"
    cmd_gpu_fryer_prepare = (
        f"docker pull {gpu_fryer_image} "
        f"|| (echo '{gpu_fryer_pull_failed_marker} for {gpu_fryer_image}; trying local tarball {gpu_fryer_tar}' >&2 "
        f"&& docker load -i {gpu_fryer_tar}) "
        f"&& docker image inspect {gpu_fryer_image} >/dev/null 2>&1 "
        f"|| (echo 'GPU Fryer image {gpu_fryer_image} is not available after pull/load; docker run uses --pull=never.' >&2 && false)"
    )
    # for OL8, needed to pass the library path and mount as it was not available on gpufryer container.
    # Making it universal to all os/arch
    try:
        ldconfig_output = subprocess.run(
            ["ldconfig", "-p"], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError) as e:
        message = f"Could not locate NVIDIA Management Library with ldconfig: {e}"
        logger.error(message)
        return False, message

    native_abi = {"x86_64": "x86-64", "aarch64": "AArch64"}.get(os.uname().machine)
    nvml_library_path = None
    for line in ldconfig_output.splitlines():
        entry, separator, path = line.strip().partition(" => ")
        if not separator or not entry.startswith("libnvidia-ml.so.1 "):
            continue
        if native_abi and native_abi not in entry:
            continue
        if os.path.isfile(path):
            nvml_library_path = os.path.realpath(path)
            break
    if nvml_library_path is None:
        message = "NVIDIA Management Library (libnvidia-ml.so.1) not found in ldconfig cache"
        logger.error(message)
        return False, message

    # The host driver path can differ from the container's library path.
    container_nvml_path = "/tmp/oci-hpc-libnvidia-ml.so.1"
    nvml_mount = (
        f"type=bind,source={nvml_library_path},"
        f"target={container_nvml_path},readonly"
    )
    cmd_gpu_fryer_run = (
        f"docker run --rm --pull=never --gpus all "
        f"--mount {shlex.quote(nvml_mount)} {gpu_fryer_image} "
        f"{command_run_time} --nvml-lib-path {container_nvml_path}"
    )

    def result_tail(result):
        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        output_text = "\n".join([stdout, stderr]).strip()
        return "\n".join(output_text.splitlines()[-20:])

    prepare_errors = []
    for attempt in range(1, 3):
        try:
            prepare_result = run_as_default_user(cmd_gpu_fryer_prepare, timeout=image_prepare_timeout)
        except subprocess.TimeoutExpired:
            error_tail = f"GPU Fryer image preparation timed out after {image_prepare_timeout} seconds"
        except Exception as e:
            error_tail = f"Failed to prepare GPU Fryer image: {e}"
        else:
            if prepare_result.returncode == 0:
                prepare_output = result_tail(prepare_result)
                if gpu_fryer_pull_failed_marker in prepare_output:
                    logger.warning(prepare_output)
                break
            error_tail = result_tail(prepare_result)

        prepare_errors.append(error_tail)
        if attempt == 1:
            logger.warning("GPU Fryer image preparation failed; retrying once:\n%s", error_tail)
        else:
            message = "GPU Fryer image preparation failed after retry; skipping GPU Fryer test"
            logger.warning("%s:\n%s", message, error_tail)
            return None, message

    try:
        run_result = run_as_default_user(cmd_gpu_fryer_run, timeout=container_run_timeout)
    except subprocess.TimeoutExpired:
        message = f"GPU Fryer container run timed out after {container_run_timeout} seconds"
        logger.error(message)
        return False, message
    except Exception as e:
        logger.error(f"Failed to run local GPU Fryer test: {e}")
        if 'run_result' in locals() and run_result.stdout:
            output = run_result.stdout.decode('utf-8', errors='replace')
            print('\n'.join(output.splitlines()[-20:]))
        return False, str(e)

    if run_result.returncode != 0:
        error_tail = result_tail(run_result)
        if (
            "Error waiting for container: Canceled:" in error_tail
            and "grpc: the client connection is closing: context canceled" in error_tail
            and "All GPUs seem healthy" in error_tail
        ):
            message = (
                "GPU Fryer test passed despite Docker/containerd client cancellation: "
                "fryer output reported all GPUs healthy"
            )
            logger.warning("%s; ignoring container error output: %s", message, error_tail)
            return True, message
        logger.error(f"Failed to run gpu-fryer:\n{error_tail}")
        return False, error_tail

    return True, "GPU Fryer test succeeded"

def run_gpu_sdc_check(gpu_ids=None):
    if not GPU_SDC_AVAILABLE:
        logger.warning("GPU SDC Checker not available - skipping SDC tests")
        return True, "GPU SDC Checker not available", {}

    try:
        # MultiGPUSDCChecker - runs all tests on all GPUs in parallel
        checker = MultiGPUSDCChecker(gpu_ids=gpu_ids)
        logger.debug(f"Running GPU SDC checks on {len(checker.checkers)} GPU(s): {list(checker.checkers.keys())}")

        # Run all tests on all GPUs
        results = checker.run_all_tests()

        # Get summary
        summary = checker.get_summary(results)

        # Check for failures
        failed_gpus = summary['aggregate_stats']['failed_gpus']
        total_errors = summary['aggregate_stats']['total_errors']

        if failed_gpus:
            message = f"GPU SDC Test Failed: {len(failed_gpus)} GPU(s) failed with {total_errors} total errors - Failed GPUs: {failed_gpus}"
            logger.error(message)
            return False, message, summary
        else:
            message = f"GPU SDC Test Succeeded: All {len(checker.checkers)} GPU(s) passed all tests"
            logger.debug(message)
            return True, message, summary

    except Exception as e:
        message = f"GPU SDC Test crashed: {str(e)}"
        logger.warning(message)
        return None, message, {}


def run_local_rvs_test(shape):
    """
    Run ROCm Validation Suite (RVS) locally on AMD nodes.
    """
    result = None
    config_path = None
    rvs_path = "/opt/rocm/bin/rvs"

    try:
        # ROCm extras packages install RVS outside the legacy bin directory.
        if not os.path.exists(rvs_path):
            rvs_candidates = sorted(
                path for path in glob.glob("/opt/rocm/extras-*/bin/rvs")
                if os.path.isfile(path) and os.access(path, os.X_OK)
            )
            if not rvs_candidates:
                logger.warning("RVS binary not found in legacy or extras directories; skipping RVS test")
                return None, "rvs-not-installed"
            elif len(rvs_candidates) > 1:
                logger.error("Multiple RVS binaries found: %s", rvs_candidates)
                return False, f"Ambiguous RVS installation: {', '.join(rvs_candidates)}"
            else:
                rvs_path = rvs_candidates[0]

        # Parameters for sanity run 
        short_params = {
            'gst': {
                "target_stress": 0.6,
                "ramp_interval": 5,
                "tolerance": 0.2,
                "max_violations": 0,
                "log_interval": 5,
                "matrix_size": 512,
                "duration": 90
            }
        }

        modules_sequence = ['gst']

        for mod in modules_sequence:
            params = short_params.get(mod, {})
            # build config (RVS v1.1.0 style)
            action = {
                "name": f"{mod}-short",
                "module": mod,
                "device": "all"
            }
            # merge params
            action.update(params)
            cfg = {"actions": [action]}

            # write temp config file
            fd, config_path = tempfile.mkstemp(prefix="rvs_config_", suffix=".json", dir="/tmp")
            os.close(fd)
            with open(config_path, "w") as f:
                json.dump(cfg, f)
                f.flush()
                os.fsync(f.fileno())
                os.chmod(config_path, 0o644)

           # logger.info("RVS configuration file saved to: %s", config_path)
            cmd_rvs = f"{rvs_path} --parallel -c {config_path}"
            logger.info("Running RVS: %s", cmd_rvs)

            # compute timeout; allow duration + buffer
            timeout = int(params.get("duration", 60) + 30)

            try:
                result = run_as_default_user(cmd_rvs, timeout=timeout)
            except subprocess.TimeoutExpired:
                tail = ""
                try:
                    if result and result.stdout:
                        tail = "\n".join(result.stdout.decode('utf-8').splitlines()[-50:])
                except Exception:
                    tail = ""
                logger.error("RVS module '%s' timed out (after %s seconds). Tail:\n%s", mod, timeout, tail)
                return False, f"RVS module {mod} timeout"

            stdout = result.stdout.decode('utf-8') if result.stdout else ""
            stderr = result.stderr.decode('utf-8') if result.stderr else ""
            combined = "\n".join([stdout, stderr]).strip()

            if result.returncode == 0:
                logger.info("RVS module '%s' passed (rc=0)", mod)
                # cleanup config for this module before next one
                if config_path and os.path.exists(config_path):
                    try:
                        os.remove(config_path)
                    except Exception:
                        pass
                config_path = None
                # small gap before next
                time.sleep(2)
                continue
            else:
                tail = "\n".join(combined.splitlines()[-50:])
                logger.error("RVS module '%s' FAILED (rc=%s). Tail:\n%s", mod, result.returncode, tail)
                # cleanup and return failure
                if config_path and os.path.exists(config_path):
                    try:
                        os.remove(config_path)
                    except Exception:
                        pass
                return False, f"RVS module {mod} failed rc={result.returncode}. Tail:\n{tail}"

        # all modules passed
        return True, "RVS suite passed"

    except Exception as e:
        tail = ""
        try:
            if result and result.stdout:
                tail = "\n".join(result.stdout.decode('utf-8').splitlines()[-50:])
        except Exception:
            tail = ""
        logger.error("Failed to run RVS short suite: %s", e)
        return False, f"Exception running RVS: {e}. Tail:\n{tail}"

    finally:
        try:
            if config_path and os.path.exists(config_path):
                os.remove(config_path)
                logger.debug("Removed temp config %s", config_path)
        except Exception:
            logger.debug("Could not remove temp config %s", config_path)

def escape_rich_markup_tags(text):
    return text.replace("[", "(").replace("]", ")")

def get_fio_command(nvme_devices):
    """
    Receive a nvme_devices list as argument and return the 
    fio command to be executed to evaluate the read performance of the
    nvme drives.

    nvme_devices = {
       "/dev/nvme0n1": {
            "numjobs": 16,
            "iodepth": 16
        },
        "/dev/nvme1n1": {
            "numjobs": 16,
            "iodepth": 16
        }
    """

    nvme_config = []
    for index, device in enumerate(nvme_devices.keys()):
        if index != 0:
            nvme_config.append("stonewall")
        nvme_config.extend([
            f"[{device}]",
            "new_group",
            f"filename={device}",
            f"numjobs={nvme_devices[device].get('numjobs')}",
            f"iodepth={nvme_devices[device].get('iodepth')}",
            ""
        ])
    fio_command = "sudo fio --output-format=json - | jq '[.jobs[] | {iops: .read.iops, drive: .jobname}]'"
    fio_command_lines = [
        "[global]",
        "name=nvme-rand-read",
        "time_based=1",
        "ramp_time=5",
        "runtime=30",
        "readwrite=randread",
        "random_generator=lfsr",
        "bs=4k",
        "ioengine=libaio",
        "direct=1",
        "group_reporting=1",
        "",
        *nvme_config,
    ]
    return fio_command, "\n".join(fio_command_lines)

def run_fio_command(fio_command, fio_config, timeout):
    """Run fio with config piped to stdin."""
    user_is_default, default_user = is_user_default()
    
    base_cmd = ["bash", "-lc", fio_command]
    if not user_is_default:
        base_cmd = ["sudo", "-u", default_user] + base_cmd
    
    result = subprocess.run(
        base_cmd,
        input=fio_config.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout
    )
    return result

def run_nvme_tests(shape, test_read=False, deviation_threshold_percentage=2):
    default_numjobs = 16
    default_iodepth = 16

    nvme_known_thresholds = {
        "INTEL SSDPF2KX038T1S": {
            "iops_threshold": 1_538_000,
            "numjobs": "16",
            "iodepth": "16"
        },
        "SAMSUNG MZWLR3T8HBLS-00AU3": {
            "iops_threshold": 430_000,
            "numjobs": "16",
            "iodepth": "16"
        },
        "SAMSUNG MZWLR3T8HCLS-00AU3": {
            "iops_threshold": 1_202_000,
            "numjobs": "16",
            "iodepth": "16"
        },
        "SAMSUNG MZWLJ7T6HALA-00AU3": {
            "iops_threshold": 430_000,
            "numjobs": "16",
            "iodepth": "16"
        },
        "7361456_ICRPC2DD2ORA6.4T": {
            "iops_threshold": 801_000,
            "numjobs": "16",
            "iodepth": "16"
        }
    }

    nvmes_number = {
        "BM.GPU.B4.8": 4,
        "BM.GPU.A100-v2.8": 4,
        "BM.GPU4.8": 4,
        "BM.GPU.H100.8": 16,
        "BM.GPU.H200.8": 8,
        "BM.GPU.B200.8": 8,
        "BM.GPU.B300.8": 8,
        "BM.GPU.B300.HS.8": 8,
        "BM.GPU.GB200.4": 4,
        "BM.GPU.GB200-v2.4": 4,
        "BM.GPU.GB200-v3.4": 4,
        "BM.GPU.GB300.4": 4,
        "BM.Optimized3.36": 1,
        "BM.HPC.E5.144": 1,
        "BM.GPU.MI300X.8": 8,
        "BM.HPC2.36": 1
    }

    result = None
    try:
        # Getting the NVME devices using nvme-cli
        detected_nvmes_dict = {}
        result = run_as_default_user("sudo nvme list -o json")
        if result.returncode == 0:
            output = json.loads(result.stdout.decode('utf-8')) if result.stdout else {}
            for device in output.get("Devices", []):
                detected_nvmes_dict[device.get("DevicePath")] = {
                    "model": device.get("ModelNumber"),
                    "numjobs": nvme_known_thresholds.get(device.get("ModelNumber"), {}).get("numjobs", default_numjobs),
                    "iodepth": nvme_known_thresholds.get(device.get("ModelNumber"), {}).get("iodepth", default_iodepth)
                }
        else:
            nvme_devices = glob.glob("/dev/nvme*n1")
            for nvme_device_path in nvme_devices:
                detected_nvmes_dict[nvme_device_path] = {
                    "numjobs": default_numjobs,
                    "iodepth": default_iodepth
                }
        
        if not detected_nvmes_dict:
            return True, "No NVME Drive found."

        # Check the NVMEs number
        if shape.rstrip("-NC") in nvmes_number:
            if nvmes_number[shape.rstrip("-NC")] != len(detected_nvmes_dict.keys()):
                return False, "Wrong number of NVME drives detected for this shape."
        else:
            if len(detected_nvmes_dict.keys())%2 != 0:
                logger.warning("Odd Number of NVME drives detected.")
        
        if not test_read:
            return True, "NVME drives detected, performance read test skipped."
        
        # Check if FIO is installed
        result = run_as_default_user("which fio")
        if result.returncode != 0:
            return False, "FIO is not installed."
            
        # Run FIO read tests
        fio_command, fio_config = get_fio_command(detected_nvmes_dict)
        result = run_fio_command(fio_command, fio_config, 1800)
        if result.returncode == 0:
            import statistics
            
            fio_command_output = json.loads(result.stdout.decode("utf-8")) if result.stdout else []
            median = statistics.median([entry['iops'] for entry in fio_command_output])

            outliers = []

            for disk_test_result in fio_command_output:
                model = detected_nvmes_dict.get(disk_test_result.get("drive")).get("model", "")
                reference = nvme_known_thresholds.get(model, {}).get("iops_threshold", median)
                if reference == 0:
                    reference = median if median > 0 else disk_test_result["iops"]

                deviation_percent = abs((disk_test_result["iops"] - reference) / reference) * 100

                if deviation_percent > deviation_threshold_percentage:
                    outliers.append(f'{disk_test_result["drive"]} > {disk_test_result["iops"]} IOPS (deviation: {deviation_percent:.2f}%)')

            if outliers:
                return False, "NVME outliers: " + escape_rich_markup_tags("; ".join(outliers))
            else:
                return True, "NVME read performance test passed."
        else:
            logger.error("NVME FIO read test failed")
            stdout = result.stdout.decode('utf-8') if result.stdout else ""
            stderr = result.stderr.decode('utf-8') if result.stderr else ""
            combined = "\n".join([stdout, stderr]).strip()
            tail = "\n".join(combined.splitlines()[-20:])
            logger.error(escape_rich_markup_tags(f"NVME FIO read test failed (rc={result.returncode}). Tail:\n{tail}"))
            return False, "fio test command execution failed."


    except subprocess.TimeoutExpired:
        logger.error("NVME FIO test timed out after 30 minutes")
        if result and result.stdout:
            out = result.stdout.decode('utf-8')
            logger.error('\n'.join(out.splitlines()[-20:]))
        return False, "Timeout after 30 minutes"
    except Exception as e:
        logger.error(f"Failed to run local NVME FIO test: {e}")
        if result and result.stdout:
            out = result.stdout.decode('utf-8')
            logger.error('\n'.join(out.splitlines()[-20:]))
            return False, escape_rich_markup_tags(str(e))
        return False, escape_rich_markup_tags(str(e))


def recommended_action(current, action):
    if action not in [None,"FabricManagerRestart","Reboot","Tag_and_Terminate"]:
        print("No action was found")
        return 0
    if action == "Reboot" or action == "FabricManagerRestart":
        if current == "Tag_and_Terminate":
            return current
        else:
            return action
    if action is None: 
        return current
    if action == "Tag_and_Terminate":
        return action

def slurm_reason(message):
    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason+=(message+"\n")
    slurm_error_count+=1

def get_reboots_count():
    result = subprocess.run(["last", "-x", "reboot"], stdout=subprocess.PIPE)
    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')
    now = datetime.now()
    one_day_ago = now - timedelta(hours=24)
    two_hours_ago = now - timedelta(hours=2)

    reboot_count_last_day = 0
    last_reboot_within_2hour = 0
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
        # Count reboots in the last 12 hours
        if reboot_time >= one_day_ago:
            reboot_count_last_day += 1

        # Check if the last reboot was within the last hour
        if reboot_time >= two_hours_ago:
            last_reboot_within_2hour += 1
    return reboot_count_last_day, last_reboot_within_2hour

if __name__ == '__main__':

    # Configure logger for active_healthcheck
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('active_healthcheck')

    if os.geteuid() == 0:
        os.makedirs("/var/log/healthchecks", exist_ok=True)
        os.chmod("/var/log/healthchecks", stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)

    file_handler = logging.FileHandler("/var/log/healthchecks/latest_active_healthcheck.log", mode='w')
    logger.addHandler(file_handler)

    version = sys.version_info
    if version >= (3, 12):
        from datetime import datetime, timedelta, UTC
    else:
        from datetime import datetime, timedelta

    # Import GPU SDC Checker if available
    try:
        from gpu_sdc_checker import GPUSDCChecker, MultiGPUSDCChecker
        GPU_SDC_AVAILABLE = True
    except ImportError:
        logger.warning("GPU SDC Checker not available - SDC tests will be skipped")
        GPU_SDC_AVAILABLE = False
        GPUSDCChecker = None
        MultiGPUSDCChecker = None
        
    action = None
    parser = argparse.ArgumentParser(description='Check Host setup')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('-slurm', '--slurm', action='store_true', help='Add a Slurm message')

    args = parser.parse_args()
    metadata = get_metadata()
    shape = metadata['shape']
    hostname = metadata['displayName']
    ocid = metadata['id']
    logger.setLevel(args.log_level)
    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Started GPU active healthcheck at: {datetime_str}")

    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason=""
    slurm_error_count=0

    try:
        host_serial = get_host_serial()
    except Exception as e:
        logger.warning(f"Failed to get host serial number with error: {e}")
        host_serial = "Unknown"
    logger.info(f"Node details: {hostname} - {host_serial} - {ocid} - {shape}")

    if "BM.GPU.MI" not in shape:
        # NVIDIA GPU's
        nccl_state,nccl_output = run_local_nccl_test(shape)
        if not nccl_state:
            logger.error(f"{hostname} - NCCL Test Failed: {nccl_output}")
            slurm_reason("Single node NCCL Test Failed")
            action = recommended_action(action, "Tag_and_Terminate")
        else:
            logger.info(f"{hostname} - NCCL Test Succeeded: {nccl_output}")
        run_time=60

        gpu_fryer_state,gpu_fryer_output = run_gpu_fryer(run_time)
        if gpu_fryer_state is None:
            logger.warning(f"{hostname} - GPU Fryer Test Skipped: {gpu_fryer_output}")
        elif not gpu_fryer_state:
            logger.error(f"{hostname} - GPU Fryer Test Failed: {gpu_fryer_output}")
            slurm_reason("Single node GPU Fryer Test Failed")
            action = recommended_action(action, "Tag_and_Terminate")
        else:
            logger.info(f"{hostname} - GPU Fryer Test Succeeded: {gpu_fryer_output}")

        # Run SDC checks
        sdc_state, sdc_output, sdc_details = run_gpu_sdc_check()
        if sdc_state is None:
            logger.warning(f"{hostname} - GPU Silent Data Corruption Test Failed: {sdc_output}")
        else:
            if not sdc_state:
                logger.error(f"{hostname} - GPU Silent Data Corruption Test Failed: {sdc_output}")
                slurm_reason("GPU SDC Test Failed")
                action = recommended_action(action, "Reboot")
            else:
                logger.info(f"{hostname} - GPU Silent Data Corruption Test Succeeded: {sdc_output}")
    else:
        #AMD GPU's: 
        rccl_state,rccl_output = run_local_rccl_test(shape)
        if not rccl_state:
            logger.error(f"{hostname} - RCCL Test Failed: {rccl_output}")
            slurm_reason("Single node RCCL Test Failed")
            action = recommended_action(action, "Tag_and_Terminate")
        else:
            logger.info(f"{hostname} - RCCL Test Succeeded: {rccl_output}")

        # --- Run RVS active healthcheck ---
        rvs_state, rvs_output = run_local_rvs_test(shape)
        if not rvs_state:
            logger.error(f"{hostname} - RVS Test Failed: {rvs_output}")
            slurm_reason("Single node RVS Test Failed")
            action = recommended_action(action, "Tag_and_Terminate")
        else:
            logger.info(f"{hostname} - RVS Test Succeeded: {rvs_output}")

    # NVME test temporarily disabled.
    # nvme_state, nvme_output = run_nvme_tests(shape, test_read=True, deviation_threshold_percentage=2)
    # if not nvme_state:
    #     if "Wrong number" in nvme_output:
    #         logger.error(f"{hostname} - NVME Test Failed: {nvme_output}")
    #         slurm_reason("One or more NVME drives failed.")
    #         action = recommended_action(action, "Tag_and_Terminate")
    #     else:
    #         logger.error(f"{hostname} - NVME FIO Test Failed: {nvme_output}")
    # else:
    #     logger.info(f"{hostname} - NVME Test Succeeded: {nvme_output}")
    
    if action == "Reboot":
        number_of_reboots,last_2hour_reboot = get_reboots_count()
        if last_2hour_reboot > 0 or number_of_reboots > 5:
            action = "Terminate"
            logger.error(f"The node has already been rebooted {last_2hour_reboot} time(s) in the last 2 hours and {number_of_reboots} in the last day")
        else:
            logger.error("Recommended Action is to Force Reboot from the console or API")
    if action == "Terminate":
        logger.error("Recommended Action is to Terminate the node and Create a SR")

    if slurm_error_count > 0 and args.slurm:
        print("Healthcheck_Active:: " + slurm_drain_reason[:-1])
        print("Healthcheck_Active:: Recommended Action:" + str(action))

    logger.info(f"Finished GPU host setup check at: {datetime_str}")

    http_server_file="/opt/oci-hpc/http_server/files/healthchecks"
    # Read the existing data from the file
    try:
        with open(http_server_file, 'r') as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.debug("Error: File not found or not in valid JSON format.")
        data={}
    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    if action is None:
        data["active_healthcheck_recommendation"] = "Healthy"
    else:
        data["active_healthcheck_recommendation"] = action
    data["active_healthcheck_time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    # Read the healthcheck.log file content
    try:
        with open("/var/log/healthchecks/latest_active_healthcheck.log", 'r') as log_file:
            data["active_healthcheck_logs"] = log_file.read(4095)  # Store log content in JSON
    except FileNotFoundError:
        logger.warning("Log file not found, initializing empty logs.")
        data["active_healthcheck_logs"] = ""
    if slurm_drain_reason:
        data["active_healthcheck_status"] = slurm_drain_reason
    else:
        data["active_healthcheck_status"] = "Healthy"
    # Write updated data back to the file
    with open(http_server_file, 'w') as file:
        try:
            json.dump(data, file, indent=4)
        except Exception as e:
            logger.error(f"Error writing to file: {e}")
