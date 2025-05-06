#!/usr/bin/env python3

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
from datetime import datetime, timedelta
from shared_logging import logger
from gpu_bw_test import BandwidthTest
from rdma_link_flapping import LinkFlappingTest
from xid_checker import XidChecker
import platform
import os
import requests
import json
import time

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
        "BM.GPU.B4.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.A100-v2.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU4.8": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.MI300X.8": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9"]
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
slurm_drain_reason = ""
slurm_error_count = 0

# Function to provide slurm reason for a node to be drained or down
def slurm_reason(message):
    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason+=(message+"\n")
    slurm_error_count+=1

# Function to provide recommendation for any health issue found
def recommended_action(current, action):
    if action not in [None,"FabricManagerRestart","Reboot","Terminate"]:
        print("No action was found")
        return 0
    if action == "Reboot" or action == "FabricManagerRestart":
        if current == "Terminate":
            return current
        else:
            return action
    if action is None: 
        return current
    if action == "Terminate":
        return action

# Check the reboot counts

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
        result = subprocess.run(['nvidia-smi', '-q'], stdout=subprocess.PIPE)
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

                # Check and handle N/A or missing values
                vol_sram = vol_sram_line[i] if i < len(vol_sram_line) else "N/A"
                vol_dram = vol_dram_line[i] if i < len(vol_dram_line) else "N/A"
                agg_sram = agg_sram_line[i] if i < len(agg_sram_line) else "N/A"
                agg_dram = agg_dram_line[i] if i < len(agg_dram_line) else "N/A"

                if vol_sram != "0" and vol_sram != "N/A":
                    logger.debug(f"Volatile SRAM Uncorrectable: {vol_sram}")
                    ecc_issues.append(f"{gpu} - Volatile SRAM Uncorrectable: {vol_sram}")
                if vol_dram != "0" and vol_dram != "N/A":
                    logger.debug(f"Volatile DRAM Uncorrectable: {vol_dram}")
                    ecc_issues.append(f"{gpu} - Volatile DRAM Uncorrectable: {vol_dram}")
                if agg_sram != "0" and agg_sram != "N/A":
                    logger.debug(f"Aggregate SRAM Uncorrectable: {agg_sram}")
                    ecc_issues.append(f"{gpu} - Aggregate SRAM Uncorrectable: {agg_sram}")
                if agg_dram != "0" and agg_dram != "N/A":
                    logger.debug(f"Aggregate DRAM Uncorrectable: {agg_dram}")
                    ecc_issues.append(f"{gpu} - Aggregate DRAM Uncorrectable: {agg_dram}")

    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

        try:
            THRESHOLD = 5
            # Try detecting AMD GPU
            result = subprocess.run(["amd-smi", "metric", "--ecc", "--json"], capture_output=True, check=True)

            # Parse JSON output
            gpu_data = json.loads(result.stdout.decode('utf-8'))
            for gpu in gpu_data:
                if gpu["ecc"]["total_uncorrectable_count"] > THRESHOLD:
                    ecc_issues.append(f"GPU {gpu['gpu']} - ECC Errors: {gpu['ecc']['total_uncorrectable_count']}")

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
            stdout=subprocess.PIPE
        )

        if result.returncode != 0:
            logger.debug(f"Check row remap command exited with error code: {result.returncode}")

    except FileNotFoundError:
        logger.warning("Skipping Row Remap Test: nvidia-smi command not found")
        return remap_issues, recommended_action

    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')
    logger.debug("Output: {}".format(output))

    for i, line in enumerate(output.split('\n')):
        if line == "":
            continue
        tmp_data = line.split(",")
        tmp_data = [x.strip() for x in tmp_data]
        if tmp_data[0] not in ["0", "No", "[N/A]"]:
            logger.debug(f"GPU: {i} - Row Remap Pending: {tmp_data[0]}")
            remap_issues.append(f"GPU: {i} Row Remap Pending: {tmp_data[0]}")
            recommended_action = "Reboot"
        #if tmp_data[1] != "0" and tmp_data[1] != "No":
        if tmp_data[1] not in ["0", "No", "[N/A]"]:
            logger.debug(f"GPU: {i} - Row Remap Failure: {tmp_data[1]}")
            recommended_action = "Terminate"
        if tmp_data[2] not in ["0", "No", "[N/A]"]:  # Add [N/A] to the list of handled values
            try:
                if int(tmp_data[2]) > 512:
                    remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable >512: {tmp_data[2]}")
                    recommended_action = "Terminate"
                else:
                    remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable <512: {tmp_data[2]}")
                    recommended_action = "Reboot"
            except ValueError:
                logger.warning(f"Invalid value for uncorrectable remapped rows: {tmp_data[2]}")
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

    shape = metadata.get('shape')
    tmp_results = []

    # Check the number of GPUs for AMD
    if shape == "BM.GPU.MI300X.8":
        try:
            result = subprocess.run(['amd-smi', 'list'], stdout=subprocess.PIPE)
            output = result.stdout.decode('utf-8')
            gpu_count = output.count("GPU")  # Count occurrences of "GPU"
            tmp_results = []
            expected_no_gpu = 8

            if gpu_count == expected_no_gpu:
                logger.info("GPU Count Test: Passed")
            else:
                logger.warning("GPU Count Test: Failed")
                tmp_results.append(f"Expected {expected_no_gpu} GPUs, found {gpu_count} using amd-smi command")

        except FileNotFoundError:
            logger.warning("Skipping GPU count test: amd-smi command not found")

        return tmp_results

    # Check the number of GPUs for NVIDIA
    try:
        result = subprocess.run(['nvidia-smi', '--list-gpus'], stdout=subprocess.PIPE)
        output = result.stdout.decode('utf-8').strip()

        # Handle "No devices found" case
        if "No devices found" in output:
            logger.error("GPU Count Test: Failed - No devices found using nvidia-smi")
            return ["No GPUs detected"]

        lines = [line for line in output.split('\n') if "GPU" in line and line.strip().startswith("GPU")]
        # Remove empty lines
        lines = [line for line in lines if line]
        if shape in ["BM.GPU.L40S-NC.4", "BM.GPU.A10.4"]:
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

# 7.1 Checks PCIe link width for NVIDIA or AMD based on instance shape.
def check_gpu_pcie():
    shape = metadata.get('shape', '')

    expected_pcie_width = 16  # Expected PCIe width

    if shape == "BM.GPU.MI300X.8":
        try:
            result = subprocess.run(['amd-smi', 'metric', '--pcie'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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

        except FileNotFoundError:
            logger.warning("GPU PCIe Width Test: Skipping - amd-smi command not found")
            return ["AMD PCIe Width Test Skipped"]

    else:
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=pcie.link.width.current', '--format=csv,noheader'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
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

    if shape in ["BM.GPU.H100.8", "BM.GPU.B4.8", "BM.GPU.A100-v2.8", "BM.GPU4.8"]:
        interface_range = range(16)
        required_authenticated = 16
    elif shape in ["BM.GPU.H200.8", "BM.GPU.B200.8", "BM.GPU.MI300X.8"]:
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
        action = "Reboot"  # Set action as needed, e.g., "Reboot" if a reset is recommended
        wpa_auth_issues.append(f"Only {authenticated_count} interfaces are AUTHENTICATED; expected at least {required_authenticated}.")
        for i in warning.keys():
            if auth_status[i] == 0:
                logger.warning(warning[i])
        logger.error("WPA Authentication Check: Failed")
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
        result = subprocess.run('nvidia-smi -q -i 0 | grep -i -A 2 Fabric', shell=True, stdout=subprocess.PIPE)
        if result.returncode != 0:
            logger.debug(f"Fabric Manager Check exited with error code: {result.returncode}")

    except FileNotFoundError:
        logger.warning("Skipping Fabric Manager test: nvidia-smi command not found")
        return fabric_manager_health

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
        result = subprocess.run(["amd-smi", "bad-pages", "--json"], capture_output=True, check=True)
        data = json.loads(result.stdout.decode('utf-8'))
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"Error executing amd-smi or parsing JSON: {e}")
        return

    errors = []

    for gpu in data:
        if gpu.get("pending") != "No bad pages found.":
            errors.append(f"Error: GPU {gpu['gpu']} has bad pages pending: {gpu['pending']}")

    if errors:
        for error in errors:
            print(error)
    else:
        logger.info("GPU Pending Bad Pages Check: Passed")

#Section 2: Main function and args to run all checks (1.2 - 16.2)
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

    args = parser.parse_args()
    metadata = get_metadata()
    shape = metadata['shape']
    logger.setLevel(args.log_level)
    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Started GPU host setup check at: {datetime_str}")

#Section 3: Function calls to run all health checks.
####################################################

    # Run everything if no arguments are provided
    run_all = not any(getattr(args, arg) for arg in vars(args) if isinstance(getattr(args, arg), bool)) or args.slurm
    # 1.3 Check OCA Status
    if run_all or args.oca_stat:
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
    if run_all or args.ecc_err:
        try:
            ecc_issues = check_ecc_errors()
        except Exception as e:
            logger.warning(f"Failed to check ECC errors with error: {e}")
            ecc_issues = []

    # 5.3 Check for row remap errors
    if run_all or args.rowremap_err:
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
    if run_all or args.gpu_pcie:    
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

    # 10.3 Check RDMA link status
    if run_all or args.rdmalink_stat:
        try:
            rdma_link_issues = check_rdma_link_status()
        except Exception as e:
            logger.warning(f"Failed to check RDMA link status with error: {e}")
            rdma_link_issues = []

    # 11.3 Check RDMA link flapping
    if run_all or args.rdmalink_flap:
        try:
            lft = LinkFlappingTest(time_interval=args.lf_interval)
            lft.get_rdma_link_failures()
            lft_issues = lft.process_rdma_link_flapping()
        except Exception as e:
            logger.warning(f"Failed to check RDMA link flapping with error: {e}")
            lft_issues = {"failures": [], "link_down": []}
 
    # 12.3 Check GPU Xid errors
    if run_all or args.xid_err: 
        try:
            xc = XidChecker()
            xid_results = xc.check_gpu_xid()
        except Exception as e:
            logger.warning(f"Failed to check GPU Xid errors with error: {e}")
            xid_results = {"status": "None", "results": {}}

    # 13.3 Check WPA Authentication status
    if run_all or args.wpa_auth:
        try:
            wpa_auth_results = check_wpa_auth(metadata)
        except Exception as e:
            logger.warning(f"Failed to get WPA Authentication status: {e}")
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

#Section 4: Summarize the results and recommend actions.
########################################################
    
    # Get host serial number and slurm drain reason
    try:
        host_serial = get_host_serial()
    except Exception as e:
        logger.warning(f"Failed to get host serial number with error: {e}")
        host_serial = "Unknown"

    logger.info(f"--------- Summary of Host setup check for {host_serial} ---------")

    # 1.4 Summarize OCA status check
    if run_all or args.oca_stat:
        if oca_state != "COMPLETED":
            logger.error(f"OCA is not ready: {oca_state}")
            slurm_reason("OCA Not completed")
    
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
    if run_all or args.ecc_err:
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
    if run_all or args.rowremap_err:
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
    if run_all or args.gpu_pcie:
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
                logger.error(f"{host_serial} - RDMA link issues: {issue}")
                slurm_reason("RDMA Link Error")
                if "signal not detected" in issue:
                    logger.info("No signal detected doesn't always come from a bad cable and require a termination for investigation")
                action = recommended_action(action, "Terminate")

    # 11.4 Summarize RDMA link flapping check
    if run_all or args.rdmalink_flap:
        if len(lft_issues["failures"]) > 0 or len(lft_issues["link_down"]) > 0:
           if len(lft_issues["failures"]) > 0:
              for issue in lft_issues["failures"]:
                  logger.error(f"{host_serial} - RDMA link flapping issues: {issue}")
                  slurm_reason("RDMA Link Flapping Error")
           if len(lft_issues["link_down"]) > 0:
              for issue in lft_issues["link_down"]:
                  logger.error(f"{host_serial} - RDMA link down issues: {issue}")
                  slurm_reason("RDMA Link Down Error")

    # 12.4 Summarize GPU Xid errors check
    if run_all or args.xid_err:
        if xid_results["status"] == "Failed":
         for xid in xid_results["results"]:
             for pci in xid_results["results"][xid]["results"]:
                 logger.error(f"{host_serial} - GPU Xid {xid} device: {pci}, {xid_results['results'][xid]['description']}")
                 slurm_reason("XID Error")

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
            logger.error(f"CPU Profile need to be 'performance'.")
            for issue in cpu_profile_issues:
                logger.error(f" - {issue}")
            slurm_reason("CPU Profile error")
            action = recommended_action(action, "Terminate")

    # 16.4 Summarize pending bad pages check for AMD
    if run_all or args.bad_page:
        if bad_page_issues:
            for issue in bad_page_issues:
                logger.error(f"{host_serial} - GPU has pending bad pages: {issue}")
            slurm_reason("GPU Bad page error")
            action = recommended_action(action, "Reboot")

    # Print recommended action and slurm message
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
        print("Healthcheck:: " + slurm_drain_reason[:-1])
        print("Healthcheck:: Recommended Action:" + str(action))

    logger.info(f"Finished GPU host setup check at: {datetime_str}")