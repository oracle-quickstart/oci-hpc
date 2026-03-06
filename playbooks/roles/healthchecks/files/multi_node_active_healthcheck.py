#!/usr/bin/env python3
import sys
import os
import argparse
import json
import requests
import subprocess
import logging
from pathlib import Path
import glob
import shlex
import time
import re

# Configure logger for multi_node_active_healthcheck
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('multi_node_active_healthcheck')

version = sys.version_info
if version >= (3, 12):
    from datetime import datetime, timedelta, UTC
else:
    from datetime import datetime, timedelta

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

def run_multi_node_nccl_test(hostfile, shape):
    paths = glob.glob('/usr/mpi/gcc/openmpi-*/bin/mpivars.sh')
    if paths:
        mpivars_path = paths[0]
    else:
        logger.info("157")

        return False,"NCCL Test Failed: No mpivars.sh found"

    increment=1024*1024*1024*9
    NCCL_DEBUG="WARN"
    exec_cmd="/opt/oci-hpc/nccl-test/build/all_reduce_perf"

    var_UCX_NET_DEVICES = shape_mapping.get(shape, {}).get('var_UCX_NET_DEVICES', '')
    if var_UCX_NET_DEVICES == "":
        logger.info("166")
        return False,f"NCCL Test Failed: Shape {shape} not found for NCCL test"
    var_NCCL_IB_HCA = shape_mapping.get(shape, {}).get('var_NCCL_IB_HCA', '')
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
            f"{exec_cmd} -b 1G -e 10G -i{increment} -n 50"
        ]
    elif shape in ("BM.GPU.H100.8", "BM.GPU.H200.8", "BM.GPU.B200.8", "BM.GPU.B300.8"):
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
            f"{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n 50"
        ]
    elif shape == "BM.GPU.GB200.4":
        mpirun_cmd = [
            "mpirun",
            "--bind-to", "none",
            "--mca", "coll", "^hcoll",
            "--mca", "plm_rsh_no_tree_spawn", "1",
            "-x", "NCCL_MNNVL_ENABLE=1",
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
            f"{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n 50"
        ]
    elif "GPU.GB" in shape:
        mpirun_cmd = [
            "mpirun",
            "--bind-to", "numa",
            "--mca", "pml", "ucx",
            "--mca", "coll", "^hcoll",
            "-x", "NCCL_MNNVL_ENABLE=1",
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
            "-x", "NCCL_NVLS_ENABLE=1",
            "-x", "NCCL_DMABUF_ENABLE=1",
            "-x", "NCCL_NET_GDR_LEVEL=SYS",
            "--np", "8",
            "--rankfile", hostfile,
            "bash","-c",
            f"{exec_cmd} -b 1G -e 16G -f 2 -g 1 -n 50"
        ]
    else:
        return False,"NCCL Test Failed: No suitable shape found for NCCL test"

    # Prepare the mpirun command as a string with proper quotations
    mpirun_str = custom_join(mpirun_cmd)
    cmd = f"source {mpivars_path} && {mpirun_str}"
    tmp_script = "/tmp/run_nccl.sh"
    with open(tmp_script, "w") as f:
        f.write(cmd)
    os.chmod(tmp_script, 0o777)
    i = 0
    while i < 5:
        i += 1
        try:
            result = subprocess.run(
                f"bash {tmp_script}",
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
                    return False,f"NCCL Test Failed: Shape {shape} not found for NCCL test"
                for line in output.splitlines():
                    if "Avg bus bandwidth" in line:
                        try:
                            bw=float(line.split()[5])
                        except:
                            return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
                        if bw < threshold:
                            return False,f"NCCL Test Failed: Avg bus bandwidth is {bw} which is less than {threshold}"
                if not bw is None:
                    return True,"NCCL Test Succeeded: Avg bus bandwidth is " + str(bw)
                else:
                    return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
            else:
                if "Invalid number of GPUs" in result.stdout or "Invalid number of GPUs" in result.stderr or 'invalid device ordinal' in result.stdout or 'invalid device ordinal' in result.stderr and i < 4:
                    continue
                return False,f"NCCL Test Failed: Failed to run nccl test. {result.stdout},{result.stderr}"
        except subprocess.TimeoutExpired:
            return False,"NCCL Test Failed: NCCL test timed out after 2 minutes"
        except Exception as e:
            if "Invalid number of GPUs" in e or 'invalid device ordinal' in e and i < 4:
                continue
            else:
                return False, f"NCCL Test Failed: Failed to run nccl test. {e}"
    return False,"NCCL Test Failed: NCCL test failed after 5 attempts"

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
            "-x", f"NCCL_SOCKET_IFNAME=eth0",
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
                if not bw is None:
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


def run_ib_write_bw(shape, server, client='localhost'):
    ib_write_bw = shape_mapping.get(shape, {}).get('ib_write_bw', '')
    if ib_write_bw == "":
        return False,"ib write bw Test Failed: Shape not found for ib write test"

    var_NCCL_IB_HCA = shape_mapping.get(shape, {}).get('var_NCCL_IB_HCA', '')
    hca_list = var_NCCL_IB_HCA.lstrip("=").split(',')

    cmd_base = "/usr/bin/ib_write_bw -F -q 2 -x 3 --report_gbits"
    results = {}
    for i in range(3):
        logger.info(f"ib write bw  Test {i+1}/3")
        for dev in hca_list:
            # Start server-side ib_write_bw over SSH
            ssh_server_cmd = f"ssh {shlex.quote(server)} 'exec {cmd_base} -d {dev}'"
            server_proc = subprocess.Popen(
                ssh_server_cmd, shell=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(1)  # Ensure server process is listening

            # Run client-side ib_write_bw over SSH
            ssh_client_cmd = f"ssh {shlex.quote(client)} '{cmd_base} -d {dev} {server}'"
            try:
                client_output = subprocess.check_output(
                    ssh_client_cmd, shell=True, timeout=20, text=True
                )
            except subprocess.CalledProcessError as e:
                return False, f"ib write bw Test Failed: Failed to run ib write bw test: {e}"
            except subprocess.TimeoutExpired:
                return False, "ib write bw Test Failed: Timeout after 20 seconds"
            # Parse output
            bw = ""
            for line in client_output.splitlines():
                if "65536      10000" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        bw = parts[2]
                        break
            results[dev] = bw
            server_proc.terminate()
        success = True
        error_dict = {}
        for key, value in results.items():
            if value != "":
                value = float(value)
                if value < ib_write_bw:
                    error_dict[key] = value
                    success = False
            else:
                error_dict[key] = None
                success = False
        if success:
            return True,"ib write bw Test Succeeded: Bandwidth for each RDMA interface is equal to or above the threshold of " + str(ib_write_bw) + " Gb/s"
        else:
            if i < 2:
                continue
            # Create a string for each key-value pair
            pairs = [f"{key} ({value})" for key, value in error_dict.items()]
            # Join them with ' and '
            interfaces_str = ' and '.join(pairs)
            # Construct the full message
            msg = f"WARNING: BW was below the threshold {ib_write_bw} Gb/s for interface {interfaces_str}"
            logger.warning(msg)
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

    success = True
    error_dict = {}
    for i in range(3):
        logger.info(f"ib write lat  Test {i+1}/3")
        for idx, dev in enumerate(hca_list):
            numa_node = 0 if idx < half else 1
            # Start server side as background process (no output)
            # Use 'nohup' to not kill process if ssh disconnects
            server_cmd = f"nohup numactl -N {numa_node} {cmd_base} -d {dev} > /dev/null 2>&1 &"
            cmd_state,cmd_output = ssh(server, server_cmd)
            if not cmd_state:
                return cmd_state,cmd_output

            time.sleep(1)  # Give server time to listen

            # On client: run ib_write_lat
            client_cmd = (
                f"numactl -N {numa_node} {cmd_base} -d {dev} {server} | grep '^ 8[[:space:]]\\+10000' | awk '{{print $6}}'"
            )
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

    if hostname == node1:
        multi_node_HC_associated_node = node2
    else:
        multi_node_HC_associated_node = node1
    data["multi_node_healthcheck_associated_node"] = multi_node_HC_associated_node

    healthcheck = healthy
    # Read the latest_multi_node_active_healthcheck.log file content

    try:
        with open("/var/log/healthchecks/latest_multi_node_active_healthcheck.log", 'r') as log_file:
            content = log_file.read()
            # Limit log content to 2048 characters, keeping start and end
            if len(content) > 4096:
                half = 2000  # Half of 2048 to keep from start and end
                content = content[:half] + "\n... [truncated] ...\n" + content[-half:]
            data["multi_node_healthcheck_logs"] = content  # Store log content in JSON

            # Check for errors in the full log content
            for line in content.splitlines():
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
            nccl_state,nccl_output = run_multi_node_nccl_test(args.hostfile, shape)
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
            logger.warning(ib_write_bw_output)
        else:
            logger.info(ib_write_bw_output)

        ib_write_lat_state,ib_write_lat_output = run_ib_write_lat(shape, server_host, client_host)
        if not ib_write_lat_state:
            logger.warning(ib_write_lat_output)
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