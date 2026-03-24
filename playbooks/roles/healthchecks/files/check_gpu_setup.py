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
2. OCA  Version Check
3. RTTCC (Round Trip Time Congestion Control) Status Check
4. ECC (Error-Correcting Code) Errors Check**:
5. Row Remap Errors Check
6. GPU Count Check
7. GPU PCIe Link Width Check
8. GPU Bandwidth Test
9. Bus Status Check
10. RDMA Link Status Check
11. RDMA Link Flapping Check
12. GPU Xid Errors Check
13. WPA Authentication Check
14. Fabric Manager Status Check
15. CPU Performance Profile Check
16. Pending Bad Pages Check (AMD GPUs)
17. Check if all interfaces have an IP address
18. Check NVLinks speeds
19. Run dcgmi health check

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

version = sys.version_info
if version >= (3, 12):
    from datetime import datetime, timedelta, UTC
else:
    from datetime import datetime, timedelta


from shared_logging import logger

SMI_TIMEOUT_SEC = 10

#Section 0: Common Functions for all Health Checks.
###################################################

# Make a request to metadata endpoint
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

# Define Mellanox devices based on GPU shape
def get_devices():
    metadata = get_metadata()
    shape = metadata['shape'] 

    shape_devices = {
        "BM.GPU.H100.8": ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.H200.8": ["mlx5_0", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_9", "mlx5_10", "mlx5_11"],
        "BM.GPU.B200.8": ["mlx5_0", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_9", "mlx5_10", "mlx5_11"],
        "BM.GPU.GB200.4": ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4"],
        "BM.GPU.GB200-v2.4": ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4"],
        "BM.GPU.GB200-v3.4": ["mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8"],
        "BM.GPU.GB300.4": ["mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_5,mlx5_6,mlx5_7,mlx5_8"],
        "BM.GPU.B4.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.A100-v2.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU4.8": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.MI300X.8": ["mlx5_0", "mlx5_2", "mlx5_3","mlx5_4", "mlx5_5", "mlx5_7", "mlx5_8", "mlx5_9"]
    }
    
    return shape_devices.get(shape, [])

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

# Function to provide slurm reason for a node to be drained or down
def slurm_reason(message):
    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason.append(message)
    slurm_error_count+=1

# Function to provide recommendation for any health issue found
def recommended_action(current, action):
    if action not in (None,"FabricManagerRestart","Reboot","Terminate","Wait_For_OCA","Reset_GPU"):
        logger.error("No action was found")
        return 0
    if action in ("Reboot", "FabricManagerRestart", "Wait_For_OCA", "Reset_GPU"):
        if current == "Terminate":
            return current
        else:
            return action
    if action is None: 
        return current
    if action == "Terminate":
        return action
    if action in ("Wait_For_OCA"):
        if current in ("FabricManagerRestart","Reboot","Terminate","Reset_GPU"):
            return current
        else:
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
def check_oca_status(log_state=False):
    try:
        with open("/var/run/oci-hpc/oci-hpc-rdma-configure.json", 'r') as file:
            data = json.load(file)

        state = data.get("state", "UNKNOWN")
        if log_state:
            logger.info(f"OCA state is: {state}")
        return state

    except FileNotFoundError:
        if log_state:
            logger.error("oci-hpc-rdma-configure.json not found.")
            return "Not Started"
    except json.JSONDecodeError:
        if log_state:
            logger.error("Failed to parse oci-hpc-rdma-configure.json.")
            return "Not Started"
# 2.1 Check if the Oracle Cloud Agent is installed and up-to-date
def get_oca_version():
    # Run the shell command
    os_name = platform.system()

    if os_name == 'Linux':
        try:
            distro = platform.linux_distribution()[0]
        except:
            import distro
            distro = distro.name()

        if 'Ubuntu' in distro:
            if not is_user_root():
                result = subprocess.run(['sudo', 'snap', 'info', 'oracle-cloud-agent'], stdout=subprocess.PIPE)
            else:
                result = subprocess.run(['snap', 'info', 'oracle-cloud-agent'], stdout=subprocess.PIPE)

            # Decode the output from bytes to string
            output = result.stdout.decode('utf-8')

            # Define the regular expression pattern for the version
            pattern = r'installed:\s+(\d+\.\d+\.\d+)'
            match = re.search(pattern, output)
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
        logger.info(f"RTTCC Disabled Check: Passed")
    else:
        logger.error(f"RTTCC Disabled Check: Failed")

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
        logger.warning(f"GPU ECC Test: Failed - nvidia-smi timed out after {SMI_TIMEOUT_SEC}s")
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
            logger.warning(f"SRAM/DRAM ECC Test: Failed - amd-smi timed out after {SMI_TIMEOUT_SEC}s")
            ecc_issues.append(f"amd-smi metric --ecc --json timed out after {SMI_TIMEOUT_SEC}s")

        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("Skipping SRAM/DRAM ECC Test: nvidia-smi | amd-smi command not found.")
            return []

        except json.JSONDecodeError as e:
            logger.error(f"Error decoding AMD JSON output: {e}")
            return []

    if not ecc_issues:
        logger.info(f"GPU ECC Test: Passed")
    else:
        logger.warning(f"GPU ECC Test: Failed")

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
        logger.warning(f"Row Remap Test: Failed - nvidia-smi timed out after {SMI_TIMEOUT_SEC}s")
        remap_issues.append(f"nvidia-smi --query-remapped-rows=remapped_rows.pending,remapped_rows.failure,remapped_rows.uncorrectable --format=csv,noheader timed out after {SMI_TIMEOUT_SEC}s")

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

    shape = metadata.get('shape')
    tmp_results = []

    # Check the number of GPUs for AMD
    if shape == "BM.GPU.MI300X.8":
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
            elif "GPU.GB" in shape:
                find_number = "2941"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_gb200
            elif shape in ["BM.GPU.GB200-v3.4"]:
                find_number = "2941"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_gb200_v3
            elif shape in ["BM.GPU.GB300.4"]:
                find_number = "2941"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_gb300                

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

    if shape == "BM.GPU.MI300X.8":
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
        logger.error(f"Devices have fallen off the bus")
    if len(bus_issues) == 0:
        logger.info("Bus Check Test: Passed")
        return(bus_issues)
    else:
        logger.warning("Bus Check Test: Failed")
        return(bus_issues)

# 10.1 Check RDMA link status for Mellanox devices.
def check_rdma_link_status():
    status = True
    
    link_issues = []
    devices = get_devices()

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
        physical_BER = re.search(r'Raw Physical BER.*', output).group().split(":")[1].strip()
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
        if not "No issue was observed" in recommendation:
            logger.debug(f"{device}: {recommendation}")
            if "Bad signal integrity" in recommendation and float(physical_BER) < 1e-07:
                logger.debug(f"Recommandation is {recommendation} but the Physical error are low enough that it can be ignored")
            elif "Bad signal integrity" in recommendation and float(physical_BER) > 1e-07:
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
        logger.info(f"RDMA Link Status Check: Passed")
    else:
        logger.warning(f"RDMA Link Status Check: Failed")
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

    if shape in ["BM.GPU.H100.8", "BM.GPU.B4.8", "BM.GPU.A100-v2.8", "BM.GPU4.8","BM.GPU.B4.8"]:
        interface_range = range(16)
        required_authenticated = 16
    elif shape in ["BM.GPU.H200.8", "BM.GPU.B200.8", "BM.GPU.MI300X.8"]:
        interface_range = range(8)
        required_authenticated = 8
    elif "GPU.GB" in shape:
        interface_range = range(4)
        required_authenticated = 0
    elif shape in ["BM.GPU.GB200-v3.4"]:
        interface_range = range(8)
        required_authenticated = 8
    elif shape in ["BM.GPU.GB300.4"]:
        interface_range = range(8)
        required_authenticated = 8
    else:
        logger.error("Unsupported machine shape.")
        return ["Unsupported machine shape."]
    
    authenticated_count = 0 
    wpa_auth_issues = []
    current_state = "None"  # Define initial state, can be updated based on actual logic
    interface_names = ["rdma" + str(i) for i in interface_range]
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
        #action = "Reboot"  # Set action as needed, e.g., "Reboot" if a reset is recommended
        wpa_auth_issues.append(f"Only {authenticated_count} interfaces are AUTHENTICATED; expected at least {required_authenticated}.")
        for i in warning.keys():
            if auth_status[i] == 0:
                logger.warning(warning[i])
        logger.warning("WPA Authentication Check: Failed")
    else:
        action = None  # No action if check passes
        logger.info("WPA Authentication Check: Passed")

    # Call the recommended_action function
    final_action = recommended_action(current_state, action)

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

# 17.1 Check if all interfaces have an IP address
def check_ip_addresses():
    devices = get_devices()    
    devices_per_interface={}
    infiniband_dir="/sys/class/infiniband"
    for device in devices:
        device_path = os.path.join(infiniband_dir, device, "device", "net")
        if os.path.exists(device_path):
            for interface in os.listdir(device_path):
                devices_per_interface[interface]=device
                break

    missing_ips=[]
    interface_map = {}
    for interface, addrs in psutil.net_if_addrs().items():
        if not interface in devices_per_interface.keys():
            continue
        ip_address = None
        # Get IPv4 address
        for addr in addrs:
            if addr.family == socket.AF_INET:
                ip_address = addr.address
                break  # Only take the first IPv4 address
        if devices_per_interface[interface] in devices and ip_address is None:
            missing_ips.append(interface)
        # Store details
        interface_map[interface] = {
            "device_name": devices_per_interface[interface],
            "interface": interface,
            "ip_address": ip_address
        }
    return missing_ips,interface_map

# 18.1 Check NVLinks speeds
def get_nvlink_speed():
    gpu_nvlink_info = {
        "BM.GPU4.8":         {"count": 12, "speed": 25,      "gpu": 8},
        "BM.GPU.B4.8":       {"count": 12, "speed": 25,      "gpu": 8},
        "BM.GPU.A100-v2.8":  {"count": 12, "speed": 25,      "gpu": 8},
        "BM.GPU.H100.8":     {"count": 18, "speed": 25,      "gpu": 8},
        "BM.GPU.H200.8":     {"count": 18, "speed": 25,      "gpu": 8},
        "BM.GPU.B200.8":     {"count": 18, "speed": 50,      "gpu": 8},
        "BM.GPU.GB200.4":    {"count": 18, "speed": 50,      "gpu": 4},
        "BM.GPU.GB200-v2.4": {"count": 18, "speed": 50,      "gpu": 4},
        "BM.GPU.GB200-v3.4": {"count": 18, "speed": 50,      "gpu": 4},
        "BM.GPU.GB300.4":    {"count": 18, "speed": 50,      "gpu": 4},
        "VM.GPU.A100.40G.1": {"count": 12, "speed": 25,      "gpu": 1},
        "VM.GPU.A100.80G.1": {"count": 12, "speed": 25,      "gpu": 1}
    }

    shape = metadata.get('shape')
    info = gpu_nvlink_info[shape]
    if not info:
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
    # Check dcgmi version
    try:
        version_out = subprocess.check_output(['dcgmi', '--version'], universal_newlines=True, timeout=10)
    except FileNotFoundError:
        logger.warning("dcgmi is not installed or not in PATH.")
        return True

    # Check if health is set up using output of `dcgmi health -c`
    try:
        health_output = subprocess.check_output(['dcgmi', 'health', '-c'], universal_newlines=True, stderr=subprocess.STDOUT, timeout=10)
        need_setup = "Error: Health watches not enabled. Please enable watches." in health_output
    except subprocess.CalledProcessError as e:
        health_output = e.output
        need_setup = "Error: Health watches not enabled. Please enable watches." in health_output

    first_time_setup = False
    if need_setup:
        # dcgmi health not set up, running `dcgmi health -s a`
        try:
            setup_output = subprocess.check_output(['dcgmi', 'health', '-s', 'a'], universal_newlines=True, stderr=subprocess.STDOUT, timeout=10)
            if "Health monitor systems set successfully." not in setup_output:
                logger.warning("Unexpected dcgmi health setup output:\n", setup_output)
                return True
            first_time_setup = True
        except subprocess.CalledProcessError as e:
            logger.warning("Error: Could not set up dcgmi health.\nOutput:", e.output)
            return True 

    # Wait 5 seconds on first setup
    if first_time_setup:
        time.sleep(5)

    # Run dcgmi health check and extract health with jq
    try:
        health_status = subprocess.check_output(
            "dcgmi health -c -j | jq -r '.body[\"Overall Health\"].value'",
            shell=True,
            #text=True,
            universal_newlines=True,
            timeout=10
        ).strip()
        status_norm = health_status.lower()

        if status_norm == "healthy":
            return True
        elif status_norm == "warning":
            logger.warning("Overall dcgmi Health is 'Warning'")
            return True
        else:
            logger.error(f"Overall Health is '{health_status}' (expected 'Healthy' or 'Warning')")
            return False
    except subprocess.CalledProcessError:
        logger.warning("Error running dcgmi health check or parsing JSON (is jq installed?).")
        return True

#Section 2: Main function and args to run all checks (1.2 - 19.2)
#################################################################

if __name__ == '__main__':
    action = None
    parser = argparse.ArgumentParser(description='Check Host setup')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('-slurm', '--slurm', action='store_true', help='Add a Slurm message')

    parser.add_argument('--oca-stat', action='store_true', help='Check the state of oca')
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
    parser.add_argument('--lf-interval', type=int, default=6, help='Link flapping interval with no flapping or link down events (default: 6 hours)')
    parser.add_argument('--xid-err', action='store_true', help='Run GPU Xid errors check')
    parser.add_argument('--wpa-auth', action='store_true', help='Run WPA authentication check')
    parser.add_argument('--fabric-mgr', action='store_true', help='Run Fabric Manager check')
    parser.add_argument('--cpu-profile', action='store_true', help='Run CPU profile check')
    parser.add_argument('--bad-page', action='store_true', help='Run bad pages check')
    parser.add_argument('--ip-address', action='store_true', help='Check if all interfaces have an IP address')
    parser.add_argument('--nvlink-speed', action='store_true', help='Check NVLinks speeds')
    parser.add_argument('--dcgmi-health', action='store_true', help='Run dcgmi health check')

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
    run_all = not any(getattr(args, arg) for arg in vars(args) if isinstance(getattr(args, arg), bool) and arg != 'log_level') or args.slurm

    # 1.3 Check OCA Status
    if (run_all or args.oca_stat) and (not ("GPU.GB" in shape or shape in ["BM.GPU.L40S.4", "BM.GPU.A10.4"])):
        try:
            oca_state = check_oca_status(log_state=True)
        except Exception as e:
            logger.warning(f"Failed to check OCA state with error: {e}")
            oca_state = "COMPLETED"

        if oca_state != "COMPLETED":
            logger.error(f"OCA is not ready: {oca_state}")
            slurm_reason("OCA Not completed")

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
    if (run_all or args.ecc_err) and "GPU" in shape and not "BM.GPU.MI" in shape:
        try:
            ecc_issues = check_ecc_errors()
        except Exception as e:
            logger.warning(f"Failed to check ECC errors with error: {e}")
            ecc_issues = []

    # 5.3 Check for row remap errors
    if (run_all or args.rowremap_err) and "GPU" in shape and not "BM.GPU.MI" in shape:
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
    if (run_all or args.gpu_pcie) and ( not "GPU.GB" in shape):    
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
        try:
            xc = XidChecker()
            xid_results = xc.check_gpu_xid()
            critical_xids = xid_results["categories"].get("critical", {})
            reset_xids = xid_results["categories"].get("gpu_reset_reboot", {})
            warning_xids  = xid_results["categories"].get("warning", {})
            if critical_xids:
                logger.debug("Xid critical error")
            elif reset_xids:
                gpu_reset_action, gpu_reset_status = gpu_reset_reboot(xc)
            elif warning_xids:
                logger.debug("Xid warning")
        except Exception as e:
            logger.warning(f"Failed to check GPU Xid errors with error: {e}")
            xid_results = {"status": "None", "results": {}}

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
            if shape == "BM.GPU.MI300X.8":
                bad_page_issues = check_bad_pages()
            else:
                bad_page_issues = None
        except Exception as e:
            logger.warning(f"Failed to check pending bad pages: {e}")
            bad_page_issues = []

    # 17.3 Check if all interfaces have an IP address
    if (run_all or args.ip_address) and ( not "GPU.GB" in shape):  
        if oca_state == "COMPLETED":
            try:
                missing_ips,ip_list = check_ip_addresses()
                if len(missing_ips) == 0:
                    logger.info("All interfaces have an IP defined: Passed")
            except Exception as e:
                logger.warning(f"Failed to get all IPS: {e}")
                missing_ips = []
        else:
            missing_ips = []

    # 18.3 Check if NVLink speed is correct
    if (run_all or args.nvlink_speed) and (shape not in ["BM.GPU.L40S.4", "BM.GPU.MI300X.8", "BM.GPU.A10.4"]):
        nvlink_speed = get_nvlink_speed()
    
    # 19.3 Check the node health using dcgmi health check
    if run_all or args.dcgmi_health:
        if shape != "BM.GPU.MI300X.8":
            try:
                dcgmi_health_check = run_dcgmi_health()
            except Exception as e:
                logger.warning(f"Failed to run dcgmi health check with error: {e}")
                dcgmi_health_check = True

            if dcgmi_health_check:
                logger.info("dcgmi health check: Passed")
        else:
            dcgmi_health_check = True

#Section 4: Summarize the results and recommend actions.
########################################################

    logger.info(f"--------- Summary of Host setup check for {host_serial} ---------")

    # 1.4 Summarize OCA status check
    if (run_all or args.oca_stat) and ( not ("GPU.GB" in shape or shape in ["BM.GPU.L40S.4", "BM.GPU.A10.4"])):
        if oca_state != "COMPLETED":
            logger.error(f"OCA is not ready: {oca_state}")
            slurm_reason("OCA Not completed")
            action = recommended_action(action, "Wait_For_OCA")
    
    # 2.4 Summarize OCA version check
    if run_all or args.oca_ver:
        if oca_version < "1.39.0":
            logger.error(f"Oracle Cloud Agent: {oca_version} needs to be updated to 1.39.0 or higher")
            slurm_reason("OCA version Error")

    # 3.4 Summarize RTTCC status check
    if run_all or args.rttcc_stat:
        if shape != "BM.GPU.MI300X.8":
            if len(rttcc_issues) > 0:
                logger.error(f"RTTCC issues: {rttcc_issues}")
                slurm_reason("RTTCC Error")

    # 4.4 Summarize ECC errors check
    if (run_all or args.ecc_err) and "GPU" in shape and not "BM.GPU.MI" in shape:
        if len(ecc_issues) > 0:
            ecc_error = False
            for issue in ecc_issues:
                if "Skipped" in issue:
                    logger.warning(f"{host_serial} - {issue}")
                else:
                    if "Aggregate" in issue:
                        logger.warning(f"{host_serial} - ECC issues: {issue}")
                    else:
                        logger.error(f"{host_serial} - ECC issues: {issue}")
                        ecc_error = True
            if ecc_error:
                slurm_reason("ECC Error")
                action = recommended_action(action, "Reboot")

    # 5.4 Summarize row remap errors check
    if (run_all or args.rowremap_err) and "GPU" in shape and not "BM.GPU.MI" in shape:
        if len(remap_results) > 0:
            remap_error = False
            for issue in remap_results:
                if "<512" in issue:
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
    if (run_all or args.gpu_pcie) and ( not "GPU.GB" in shape):
            if gpu_pcie_results:
                logger.error(f"{host_serial} - GPU PCIe Width: {gpu_pcie_results}")
                slurm_reason("GPU PCIe Width Error")
                action = recommended_action(action, "Terminate")

    # 8.4 Summarize GPU bandwidth test
    if run_all or args.bw_test:
        if bwt_results != None:
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
                logger.warning(f"{host_serial} - RDMA link issues: {issue}")
                #slurm_reason("RDMA Link Error")
                if "signal not detected" in issue:
                    logger.info("No signal detected doesn't always come from a bad cable and require a termination for investigation")
                #action = recommended_action(action, "Terminate")

    # 11.4 Summarize RDMA link flapping check
    if run_all or args.rdmalink_flap:
        if len(lft_issues["failures"]) > 0 or len(lft_issues["link_down"]) > 0:
           if len(lft_issues["failures"]) == 1:
              issue = lft_issues["failures"][0]
              logger.warning(f"{host_serial} - RDMA link flapping issues: {issue}")
           elif len(lft_issues["failures"]) > 1:
              for issue in lft_issues["failures"]:
                  logger.warning(f"{host_serial} - RDMA link flapping issues: {issue}")
                  #slurm_reason("RDMA Link Flapping Error")
           if len(lft_issues["link_down"]) == 1:
              issue = lft_issues["link_down"][0]
              logger.warning(f"{host_serial} - RDMA link down issues: {issue}")
           elif len(lft_issues["link_down"]) > 1:
              for issue in lft_issues["link_down"]:
                  logger.warning(f"{host_serial} - RDMA link down issues: {issue}")
                  #slurm_reason("RDMA Link Down Error")

    # 12.4 Summarize GPU Xid errors check
    if run_all or args.xid_err:
        critical_xids = xid_results["categories"].get("critical", {})
        reset_xids = xid_results["categories"].get("gpu_reset_reboot", {})
        warning_xids  = xid_results["categories"].get("warning", {})

        # Log & set action for Xids
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
                logger.warning(f"{host_serial} - WPA authentication issue: {issue}")
            #slurm_reason("WPA Auth Error")
            #action = recommended_action(action, "Reboot")

    # 14.4 Summarize Fabric Manager check
    if run_all or args.fabric_mgr:
        if not fabric_manager_health:
            logger.error(f"{host_serial} - Fabric Manager not started")
            slurm_reason("Fabric Manager Error")
            action = recommended_action(action, "FabricManagerRestart")

    # 15.4 Summarize CPU profile check
    if run_all or args.cpu_profile:
        if cpu_profile_issues:
            logger.warning(f"CPU Profile need to be 'performance'.")
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

    # 17.4 Summarize all interfaces have an IP address check
    if (run_all or args.ip_address) and ( not "GPU.GB" in shape):
        if len(missing_ips) > 0:
            logger.error(f"Missing IPs for these interfaces: {','.join(missing_ips)}")
            slurm_reason("Missing IPs")
            action = recommended_action(action, "Reboot")
    
    # 18.4 Summarize NVLink speed check
    if (run_all or args.nvlink_speed) and (shape not in ["BM.GPU.L40S.4", "BM.GPU.MI300X.8", "BM.GPU.A10.4"]):
        if not nvlink_speed:
            logger.error(f"NVLink speed Error for one or more GPUs")
            slurm_reason("NVLink speed Error")
            action = recommended_action(action, "Reboot")

    # 19.4 Summarize dcgmi health check
    if run_all or args.dcgmi_health:
        if not dcgmi_health_check:
            logger.error(f"{host_serial} - dcgmi health check failed. Run `dcgmi health -c` to get full output.")
            slurm_reason("dcgmi health check failed")
            action = recommended_action(action, "Reboot")

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

    if slurm_error_count > 0 and args.slurm:
        logger.error("Healthcheck:: " + ", ".join(slurm_drain_reason))
        logger.error("Healthcheck:: Recommended Action:" + str(action))

    logger.info(f"Finished GPU host setup check at: {datetime_str}")