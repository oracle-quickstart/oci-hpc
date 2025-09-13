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

# Configure logger for multi_node_active_healthcheck
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('multi_node_active_healthcheck')

file_handler = logging.FileHandler("/tmp/latest_multi_node_active_healthcheck.log", mode='w')
logger.addHandler(file_handler)

version = sys.version_info
if version >= (3, 12):
    from datetime import datetime, timedelta, UTC
else:
    from datetime import datetime, timedelta

def get_metadata():
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()
    
def custom_join(cmd_list):
    return ' '.join(('^hcoll' if x == '^hcoll' else shlex.quote(x)) for x in cmd_list)

def run_multi_node_nccl_test(hostfile, shape):

    paths = glob.glob('/usr/mpi/gcc/openmpi-*/bin/mpivars.sh')
    if paths:
        mpivars_path = paths[0]
    else:
        logger.error(f"No mpivars.sh found")
        return False,"No mpivars.sh found"

    # Set defaults
    shape_mapping = {
        "BM.GPU.B4.8": {
            "var_UCX_NET_DEVICES": "mlx5_0:1",
            "threshold": 185
        },
        "BM.GPU.A100-v2.8": {
            "var_UCX_NET_DEVICES": "mlx5_0:1",
            "threshold": 185
        },
        "BM.GPU4.8": {
            "var_UCX_NET_DEVICES": "mlx5_4:1",
            "threshold": 185
        },
        "BM.GPU.H100.8": {
            "var_UCX_NET_DEVICES": "eth0",
            "threshold": 440
        },
        "BM.GPU.H200.8": {
            "var_UCX_NET_DEVICES": "eth0",
            "threshold": 440
        },
        "BM.GPU.B200.8": {
            "var_UCX_NET_DEVICES": "eth0",
            "threshold": 440
        }
    }

    increment=1024*1024*1024*9
    NCCL_DEBUG="WARN"
    exec_cmd="/opt/oci-hpc/nccl-test/build/all_reduce_perf"

    var_UCX_NET_DEVICES = shape_mapping.get(shape, {}).get('var_UCX_NET_DEVICES', '')
    if var_UCX_NET_DEVICES == "":
        logger.error("Shape not found for multi-node NCCL test")
        return False,"Shape not found for multi-node NCCL test"

    if shape in ("BM.GPU.B4.8", "BM.GPU.A100-v2.8", "BM.GPU4.8"):
        mpirun_cmd = [
            "mpirun", "--mca", "pml", "ucx",
            "--bind-to", "numa",
            "--mca", "coll", "^hcoll",
            "-x", "UCX_TLS=ud,self,sm",
            "-x", f"UCX_NET_DEVICES={var_UCX_NET_DEVICES}",
            "-x", "HCOLL_ENABLE_MCAST_ALL=0",
            "-x", "coll_hcoll_enable=0",
            "-x", "NCCL_ALGO=Ring",
            "-x", f"NCCL_DEBUG={NCCL_DEBUG}",
            "--np", "16",
            "--hostfile", hostfile,
            exec_cmd, "-b1G", "-e10G", f"-i{increment}", "-n", "100"
        ]
    elif shape in ("BM.GPU.H100.8", "BM.GPU.H200.8", "BM.GPU.B200.8"):
        mpirun_cmd = [
            "mpirun", "--mca", "pml", "ucx",
            "--bind-to", "numa",
            "-npernode", "8",
            "--mca", "coll", "^hcoll",
            "-x", "HCOLL_ENABLE_MCAST_ALL=0",
            "-x", "coll_hcoll_enable=0",
            "-x", "UCX_TLS=tcp",
            "-x", f"UCX_NET_DEVICES={var_UCX_NET_DEVICES}",
            "-x", "RX_QUEUE_LEN=8192",
            "-x", "IB_RX_QUEUE_LEN=8192",
            "-x", f"NCCL_DEBUG={NCCL_DEBUG}",
            "--np", "16",
            "--hostfile", hostfile,
            exec_cmd, "-b", "1G", "-e", "16G", "-f", "2", "-g", "1", "-n", "50"
        ]
    else:
        logger.error("No suitable shape found for NCCL multi-node test")
        return False,"No suitable shape found for NCCL multi-node test"

    # Prepare the mpirun command as a string with proper quotations
    mpirun_str = custom_join(mpirun_cmd)
    cmd = f"source {mpivars_path} && {mpirun_str}"
    logger.info(cmd)

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

        healthy = "Healthy"
        potentially_bad = "Potentially Bad"
        if result.returncode == 0:
            output = result.stdout
            logger.info(output)
            bw=None
            threshold = shape_mapping.get(shape, {}).get("threshold")
            if threshold == "":
                logger.error("Shape not found for multi-node NCCL test")
                return False,"Shape not found for multi-node NCCL test"
            for line in output.splitlines():
                if "Avg bus bandwidth" in line:
                    try:
                        bw=float(line.split()[5])
                    except:
                        logger.error(f"NCCL Test Failed: Avg bus bandwidth could not be found")
                        logger.info(f"result: {potentially_bad}")
                        return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
                    if bw < threshold:
                        logger.error(f"NCCL Test Failed: Avg bus bandwidth is {bw}")
                        logger.info(f"result: {potentially_bad}")
                        return False,f"NCCL Test Failed: Avg bus bandwidth is less than {threshold}"
            if not bw is None:
                logger.info(f"NCCL Test Succeeded: Avg bus bandwidth is {bw}")
                logger.info(f"result: {healthy}")
                return True,"NCCL Test Succeeded: Avg bus bandwidth is "+str(bw)
            else:
                logger.error(f"NCCL Test Failed: Avg bus bandwidth could not be found")
                logger.info(f"result: {potentially_bad}")
                return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
        else:
            logger.error(f"Failed to run multi-node nccl test: {result.stderr}")
            logger.info(f"result: {potentially_bad}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        logger.info("NCCL test timed out after 2 minutes")
        logger.info(f"result: {potentially_bad}")
        return False, "Timeout after 2 minutes"
    except Exception as e:
        logger.error(f"Failed to run multi-node nccl test: {e}")
        logger.info(f"result: {potentially_bad}")
        return False, str(e)

if __name__ == '__main__':
    action = None
    parser = argparse.ArgumentParser(description='Run multi-node NCCL active test')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('-f', '--hostfile', required=True, type=str, help='Hostfile with one host per line')

    args = parser.parse_args()
    if not args.hostfile.strip():
        logger.error("Error: --hostfile argument cannot be empty", flush=True)
        sys.exit(1)
    metadata = get_metadata()
    shape = metadata['shape']
    hostname = metadata['displayName']
    ocid = metadata['id']
    logger.setLevel(args.log_level)
    datetime_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Started multi-node active healthcheck at: {datetime_str}")

    nccl_state,nccl_output = run_multi_node_nccl_test(args.hostfile, shape)
    if not nccl_state:
        logger.error(f"Multi-node NCCL Test Failed: {nccl_output}")

    datetime_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info(f"Finished multi-node active healthcheck at: {datetime_str}")