#!/usr/bin/env python3

import subprocess
import re
import argparse
from shared_logging import logger
from gpu_bw_test import BandwidthTest
from rdma_link_flapping import LinkFlappingTest
from xid_checker import XidChecker
import platform
import os
import requests
import glob
import json
import socket
import psutil
import time
import sys

version = sys.version_info
if version >= (3, 12):
    from datetime import datetime, timedelta, UTC
else:
    from datetime import datetime, timedelta

def get_metadata():
    """ Make a request to metadata endpoint """
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()

def is_user_root():
    # Check if the user is root
    if os.geteuid() != 0:
        logger.debug("User is not root!")
        return False
    return True

def get_devices():
    # Define Mellanox devices based on GPU shape

    metadata = get_metadata()
    shape = metadata['shape']

    shape_devices = {
        "BM.GPU.H100.8": ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.B4.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.A100-v2.8": ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU4.8": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"],
        "BM.GPU.MI300X.8": ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9"]
    }
    if shape not in shape_devices:
        logger.info(f"RTTCC check not required for shape: {shape}")
        return []
    return shape_devices[shape]


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
def check_oca_status():
    try:
        with open("/var/run/oci-hpc/oci-hpc-rdma-configure.json", 'r') as file:
            data = json.load(file)

        state = data.get("state", "UNKNOWN")
        logger.info(f"oci-hpc-rdma-configure state is: {state}")
        return state

    except FileNotFoundError:
        logger.error("oci-hpc-rdma-configure.json not found.")
    except json.JSONDecodeError:
        logger.error("Failed to parse oci-hpc-rdma-configure.json.")

def check_rttcc_status():
    """Check RTTCC status for supported GPU shapes and return status log."""
    link_status = []

    devices = get_devices()
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

def check_ecc_errors():
    """Check ECC errors for NVIDIA or AMD GPUs."""
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

def check_row_remap_errors():
    remap_issues = []
    recommended_action=None
    if shape == "BM.GPU.MI300X.8":
        pass
    else:
        try:
            # Run the nvidia-smi -q command
            result = subprocess.run(['nvidia-smi', '--query-remapped-rows=remapped_rows.pending,remapped_rows.failure,remapped_rows.uncorrectable', '--format=csv,noheader'], stdout=subprocess.PIPE)

            if result.returncode != 0:
                logger.debug(f"Check row remap command exited with error code: {result.returncode}")

        except FileNotFoundError:
            logger.warning("Skipping Row Remap Test: nvidia-smi command not found")
            return []
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
                #remap_issues.append(f"GPU: {i} Row Remap Failure: {tmp_data[1]}")
                recommended_action = "Terminate"
            if tmp_data[2] != "0" and tmp_data[2] != "No":
                logger.debug(f"GPU: {i} - Row Remap Uncorrectable: {tmp_data[2]}")
                if int(tmp_data[2]) > 512:
                    remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable >512: {tmp_data[2]}")
                    recommended_action = "Terminate"
                else:
                    remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable <512: {tmp_data[2]}")# Check if there are ecc_issues
                    recommended_action = "Reboot"
        if len(remap_issues) == 0:
            logger.info("GPU Remap Test: Passed")
        else:
            logger.warning("GPU Remap Test: Failed")
    return remap_issues, recommended_action

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

def get_host_serial():
    # Run the shell command
    if not is_user_root():
        result = subprocess.run(['sudo', 'dmidecode', '-s', 'system-serial-number'], stdout=subprocess.PIPE)
    else:
        result = subprocess.run(['dmidecode', '-s', 'system-serial-number'], stdout=subprocess.PIPE)

    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')

    # Return the serial number
    return output.strip()

def check_bus():
    # Check to see if any devices have fallen of the bus
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

def check_gpu_count():

    lspci_expected_results_gpu = [  '0f:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '2d:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '44:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '5b:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '89:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                'a8:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                'c0:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                'd8:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)'
                             ]
    lspci_expected_results_l40s = [  '16:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)',
                                     '38:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)',
                                     '82:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)',
                                     'ac:00.0 3D controller: NVIDIA Corporation Device 26b9 (rev a1)'
                                ]
    lspci_expected_results_a10 = [  '17:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)',
                                    '31:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)',
                                    'b1:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)',
                                    'ca:00.0 3D controller: NVIDIA Corporation GA102GL [A10] (rev a1)'
                                ]

    metadata=get_metadata()
    shape=metadata['shape']
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
        output = result.stdout.decode('utf-8')
        lines = output.split('\n')
        # remove empty lines
        lines = [line for line in lines if line]
        if shape == "BM.GPU.L40S-NC.4" or shape == "BM.GPU.A10.4":
            if len(lines) == 4:
                logger.info("GPU Count Test: Passed")
            else:
                logger.warning("GPU Count Test: Failed")
                tmp_results.append(f"Expected 4 GPUs, found {len(lines)} using nvidia-smi command")
            return tmp_results
        elif len(lines) == 8:
            logger.info("GPU Count Test: Passed")
        else:
            logger.warning("GPU Count Test: Failed")
            tmp_results.append(f"Expected 8 GPUs, found {len(lines)} using nvidia-smi command")
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
            metadata=get_metadata()
            shape=metadata['shape']
            find_number = ""
            expected_gpus = ""
            lspci_expected_results = ""
            if shape == "BM.GPU.L40S-NC.4":
                find_number = "26b9"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_l40s
            elif shape == "BM.GPU.A10.4":
                find_number = "GA102GL"
                expected_gpus = 4
                lspci_expected_results = lspci_expected_results_a10
            else:
                find_number = "2330"
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
            if len(tmp_results) == 8:
                logger.info("GPU Count Test: Passed")
            else:
                logger.warning("GPU Count Test: Failed")
            return missing_gpus
        except FileNotFoundError:
            logger.warning("Skipping GPU count test: nvidia-smi and lspci commands not found")
            return None

def check_gpu_pcie():
    """Checks PCIe link width for NVIDIA or AMD based on instance shape."""
    # A100, H100, H200 and MI300X have x16
    metadata = get_metadata()
    shape = metadata.get('shape', '')

    expected_pcie_width = 16  # Expected PCIe width

    if shape == "BM.GPU.MI300X.8":
        try:
            # Run amd-smi for AMD GPUs
            result = subprocess.run(['amd-smi', 'metric', '--pcie'], stdout=subprocess.PIPE, check=True)

            if result.returncode != 0:
                logger.warning("GPU PCIe Width Test: Command amd-smi failed")
                return None
            else:
                output = result.stdout.decode('utf-8')

                # Extract PCIe WIDTH values correctly
                pcie_widths = re.findall(r'^\s*WIDTH:\s*(\d+)', output, re.MULTILINE)
                pcie_widths = list(map(int, pcie_widths)) if pcie_widths else []

                if all(width == expected_pcie_width for width in pcie_widths):
                    logger.info("GPU PCIe Width Test: Passed")
                else:
                    logger.warning("GPU PCIe Width Test: Failed")
                    return expected_pcie_width - int(sum(pcie_widths) / len(pcie_widths))

        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("GPU PCIe Width Test: Skipping - amd-smi command not found")
            return None

    else:
        try:
            # Run nvidia-smi for NVIDIA GPUs
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=pcie.link.width.current', '--format=csv,noheader'],
                stdout=subprocess.PIPE, check=True
            )

            if result.returncode != 0:
                logger.warning("GPU PCIe Width Test: Command nvidia-smi failed")
                return None

            output = result.stdout.decode('utf-8').strip()
            widths = list(map(int, output.split("\n")))

            if all(width == expected_pcie_width for width in widths):
                logger.info("GPU PCIe Width Test: Passed")
            else:
                logger.warning("GPU PCIe Width Test: Failed")
                return expected_pcie_width - int(sum(widths) / len(widths))

        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("GPU PCIe Width Test: Skipping - nvidia-smi command not found")
            return None

    return None

def check_wpa_auth(metadata):
    # Determine the shape and required authenticated count
    shape = metadata.get('shape')
    if shape in ["BM.GPU.H100.8", "BM.GPU.B4.8", "BM.GPU.A100-v2.8", "BM.GPU4.8"]:
        interface_range = range(16)
        required_authenticated = 16
    elif shape in ["BM.GPU.H200.8", "BM.GPU.MI300X.8"]:
        interface_range = range(8)
        required_authenticated = 8 
    else:
        logger.error("Unsupported machine shape.")
        return ["Unsupported machine shape."]

    authenticated_count = 0 
    wpa_auth_issues = []
    current_state = "None"  # Define initial state, can be updated based on actual logic
    interface_names=["rdma"+str(i) for i in interface_range]
    auth_status={key: 0 for key in interface_names}
    warning={key: [] for key in interface_names}
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
                    warning[interface]=result.stderr.decode('utf-8').rstrip("\n")
                for line in result.stdout.decode('utf-8').splitlines():
                    if "Supplicant PAE state" in line:
                        if "AUTHENTICATED" in line:
                            auth_status[interface]=1
                        break
            except subprocess.CalledProcessError as e:
                wpa_auth_issues.append(f"Error checking {interface}: {e}")
                logger.warning(f"Error checking {interface}: {e}")
        authenticated_count=sum(auth_status.values())
        if authenticated_count >= required_authenticated:
            break
        else:
            time.sleep(5)
        # Determine action based on authentication result
    if authenticated_count < required_authenticated:
        action = "Reboot"  # Set action as needed, e.g., "Reboot" if a reset is recommended
        wpa_auth_issues.append(f"Only {authenticated_count} interfaces are AUTHENTICATED; expected at least {required_authenticated}.")
        for i in warning.keys():
            if auth_status[i]==0:
                logger.warning(warning[i])
        logger.error("WPA Authentication Check: Failed")
    else:
        action = None  # No action if check passes
        logger.info("WPA Authentication Check: Passed")

    # Call the recommanded_action function
    final_action = recommended_action(current_state, action)

    return wpa_auth_issues if wpa_auth_issues else []

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

def get_current_cpu_profile():
    """Retrieve online CPUs and check if their profile is set to 'performance'."""
    try:
        # Get instance metadata
        metadata = get_metadata()
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

def check_ip_addresses(metadata):

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

def slurm_reason(message):
    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason+=(message+"\n")
    slurm_error_count+=1

def recommended_action(current, action):
    if action not in [None,"FabricManagerRestart","Reboot","LiveFix","Reboot&LiveFix","Terminate"]:
        print("No action was found")
        return 0
    if action == "Reboot" or action == "FabricManagerRestart":
        if current == "Terminate":
            return current
        elif current == "LiveFix":
            return "Reboot&LiveFix"
        elif current == "Reboot&LiveFix":
            return "Reboot&LiveFix"
        else:
            return action
    if action == "LiveFix":
        if current == "Terminate":
            return current
        elif current == "Reboot":
            return "Reboot&LiveFix"
        elif current == "Reboot&LiveFix":
            return "Reboot&LiveFix"
        elif current == "FabricManagerRestart":
            return "Reboot&LiveFix"
        else:
            return action
    if action is None: 
        return current
    if action == "Terminate":
        return action

if __name__ == '__main__':
    
    action = None
    parser = argparse.ArgumentParser(description='Check Host setup')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('--bw-test', dest='bw_test', action='store_true', default=False, help='Run GPU bandwidth test (default: False)')
    parser.add_argument('--bw-test-exe', dest='bw_test_exe', help='Location to cuda-sampels bandwidthTest')
    parser.add_argument('--lf-interval', dest='lf_interval', default=6, type=int, help='Link flapping interval with no flapping or link down events (default: 6 (hours))')
    parser.add_argument('-a','--all', dest='run_all', action='store_true', default=False, help='Run all checks (default: False)')
    parser.add_argument('-slurm','--slurm', dest='slurm', action='store_true', default=False, help='Add a Slurm message')
    parser.add_argument('-wa', '--wpa-auth', action="store_true", default=False, help="Run WPA authentication check")
    args = parser.parse_args()

    logger.setLevel(args.log_level)

    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Started GPU host setup check at: {datetime_str}")

    metadata=get_metadata()
    shape=metadata['shape']

    # Check for OCA Version
    try:
        oca_version = get_oca_version()
    except Exception as e:
        logger.warning(f"Failed to get Oracle Cloud Agent version with error: {e}")
        oca_version = "Unknown"

    # Check for OCA status
    try:
        oca_issues = check_oca_status()
    except Exception as e:
        logger.warning(f"Failed to check OCA state with error: {e}")
        oca_issues = []

    # Check for RTTCC Issues
    if shape != "BM.GPU.H200.8":
        try:
            rttcc_issues = check_rttcc_status()
        except Exception as e:
            logger.warning(f"Failed to check RTTCC status with error: {e}")
            rttcc_issues = []
    else:
        rttcc_issues = []
    # Check for ECC errors
    try:
        ecc_issues = check_ecc_errors()
    except Exception as e:
        logger.warning(f"Failed to check ECC errors with error: {e}")
        ecc_issues = []

    # Check for row remap errors
    try:
        remap_results,row_remap_action = check_row_remap_errors()
    except Exception as e:
        logger.warning(f"Failed to check row remap errors with error: {e}")
        remap_results = []

    # Check for RDMA link status
    try:
        rdma_link_issues = check_rdma_link_status()
    except Exception as e:
        logger.warning(f"Failed to check RDMA link status with error: {e}")
        rdma_link_issues = []

    # Check for RDMA link flapping
    try:
        metadata=get_metadata()
        shape=metadata['shape']
        if shape == "BM.GPU.H100.8" or shape == "BM.GPU.B4.8" or shape == "BM.GPU.A100-v2.8" or shape == "BM.GPU4.8" or shape == "BM.GPU.H200.8" or shape == "BM.GPU.MI300X.8":
            lft = LinkFlappingTest(time_interval=args.lf_interval)
            lft.get_rdma_link_failures()
            lft_issues = lft.process_rdma_link_flapping()
        else:
            logger.info(f"RDMA Link Flapping/Down test not required")
            lft_issues = {"failures": [], "link_down": []}
    except Exception as e:
        logger.warning(f"Failed to check RDMA link flapping with error: {e}")
        lft_issues = {"failures": [], "link_down": []}

    # Check for GPU Xid errors
    if shape == "BM.GPU.MI300X.8":
        pass
    else:
        try:
            xc = XidChecker()
            xid_results = xc.check_gpu_xid()
        except Exception as e:
            logger.warning(f"Failed to check GPU Xid errors with error: {e}")
            xid_results = {"status": "None", "results": {}}

    # Check GPU bandwidth
    bwt_results = None
    try:
        if args.bw_test == True or args.run_all == True:
            if args.bw_test_exe:
                bwt = BandwidthTest(bw_test_exe=args.bw_test_exe)
            else:
                bwt = BandwidthTest()
            bwt.measure_gpu_bw()
            bwt_results = bwt.validate_results()
    except Exception as e:
        logger.warning(f"Failed to check GPU bandwidth with error: {e}")
        bwt_results = None

    # Check the bus
    try:
        bus_results = check_bus()
    except Exception as e:
        logger.warning(f"Failed to check the bus with error: {e}")
        bus_results = None

    # Check the number of GPUs
    try:
        gpu_results = check_gpu_count()
    except Exception as e:
        logger.warning(f"Failed to check the number of GPUs with error: {e}")
        gpu_results = None

    # Check GPU PCIe Widths
    try:
        gpu_pcie_results = check_gpu_pcie()
    except Exception as e:
        logger.warning(f"Failed to check GPU PCIe Width with error: {e}")
        gpu_pcie_results = None

    # Check WPA authentication if the option is set
    wpa_auth_results = None
    if args.wpa_auth:
        try:
            metadata = get_metadata()
            wpa_auth_results = check_wpa_auth(metadata)
        except Exception as e:
            logger.warning(f"Failed to get WPA Authentication status: {e}")
            wpa_auth_results = None

    # Check all IPS
    missing_ips = []
    try:
        metadata = get_metadata()
        missing_ips,ip_list = check_ip_addresses(metadata)
        if len(missing_ips) == 0:
            logger.info("All interfaces have an IP defined: Passed")
    except Exception as e:
        logger.warning(f"Failed to get all IPS: {e}")
        missing_ips = []

    # Check for Fabric Manager Started
    if shape == "BM.GPU.H100.8" or shape == "BM.GPU.H200.8":
        try:
            fabric_manager_health = check_fabric_manager()
        except Exception as e:
            logger.warning(f"Failed to check Fabric Manager with error: {e}")
            fabric_manager_health = True

        if fabric_manager_health:
            logger.info("Fabric Manager Running: Passed")
    else:
        fabric_manager_health=True

    # Check CPU Profile is performance
    try:
        cpu_profile_issues = get_current_cpu_profile()
    except Exception as e:
        logger.warning(f"Failed to check CPU profile with error: {e}")
        cpu_profile_issues = []

    # Check if amd gpu has pending bad pages
    try:
        if shape == "BM.GPU.MI300X.8":
            bad_page_issues = check_bad_pages()
        else:
            bad_page_issues = None
    except Exception as e:
        logger.warning(f"Failed to check pending bad pages: {e}")
        bad_page_issues = []

    # Summarize the results
    try:
        host_serial = get_host_serial()
    except Exception as e:
        logger.warning(f"Failed to get host serial number with error: {e}")
        host_serial = "Unknown"

    slurm_drain_reason = ""
    slurm_error_count = 0

    logger.info(f"--------- Summary of Host setup check for {host_serial} ---------")

    if oca_version < "1.39.0":
        logger.error(f"Oracle Cloud Agent: {oca_version} needs to be updated to 1.39.0 or higher")
        slurm_reason("OCA version Error")

    if shape != "BM.GPU.MI300X.8":
        if len(rttcc_issues) > 0:
            logger.error(f"RTTCC issues: {rttcc_issues}")
            slurm_reason("RTTCC Error")

    if len(oca_issues) > 0:
        logger.error(f"OCA is not ready: {oca_issues}")
        slurm_reason("OCA Not completed")
    
    if len(ecc_issues) > 0:
        ecc_error=False
        for issue in ecc_issues:
            if "Skipped" in issue:
                logger.warning(f"{host_serial} - {issue}")
            else:
                if "Aggregate" in issue:
                    logger.warning(f"{host_serial} - ECC issues: {issue}")
                else:
                    logger.error(f"{host_serial} - ECC issues: {issue}")
                    ecc_error=True
        if ecc_error:
            slurm_reason("ECC Error")
            action = recommended_action(action, "Reboot")

    if len(remap_results) > 0:
        remap_error=False
        for issue in remap_results:
            if "<512" in issue:
                logger.warning(f"{host_serial} - {issue}")
            else:
                logger.error(f"{host_serial} - {issue}")
                remap_error=True
        if remap_error:
            slurm_reason("Remap Error")
            action = recommended_action(action, row_remap_action)

    if shape == "BM.GPU.MI300X.8":
        pass
    else:
        if xid_results["status"] == "Failed":
            for xid in xid_results["results"]:
                for pci in xid_results["results"][xid]["results"]:
                    logger.error(f"{host_serial} - GPU Xid {xid} device: {pci}, {xid_results['results'][xid]['description']}")
                    slurm_reason("XID Error")
                    action = recommended_action(action, "Reboot")

    if len(rdma_link_issues) > 0:
        for issue in rdma_link_issues:
            logger.error(f"{host_serial} - RDMA link issues: {issue}")
            slurm_reason("RDMA Link Error")
            if "signal not detected" in issue:
                logger.info("No signal detected doesn't always come from a bad cable and require a termination for investigation")
                action = recommended_action(action, "Terminate")
            else:
                action = recommended_action(action, "LiveFix")

    if len(lft_issues["failures"]) > 0 or len(lft_issues["link_down"]) > 0:
        if len(lft_issues["failures"]) > 0:
            for issue in lft_issues["failures"]:
                logger.error(f"{host_serial} - RDMA link flapping issues: {issue}")
                slurm_reason("RDMA Link Flapping Error")
                action = recommended_action(action, "LiveFix")
        if len(lft_issues["link_down"]) > 0:
            for issue in lft_issues["link_down"]:
                logger.error(f"{host_serial} - RDMA link down issues: {issue}")
                slurm_reason("RDMA Link Down Error")
                action = recommended_action(action, "LiveFix")

    if bwt_results != None:
        if bwt_results["status"] == "Failed":
            for issue in bwt_results["issues"]:
                logger.error(f"{host_serial} - GPU bandwidth issues: {issue}")
                slurm_reason("GPU Bwt Error")
                action = recommended_action(action, "Terminate")

    if bus_results:
        logger.error(f"{host_serial} - Bus issues: {bus_results}")
        slurm_reason("GPU Bus Error")
        action = recommended_action(action, "Terminate")

    if gpu_results:
        logger.error(f"{host_serial} - Missing GPU(s): {gpu_results}")
        slurm_reason("Missing GPU Error")
        action = recommended_action(action, "Reboot")

    if gpu_pcie_results:
        logger.error(f"{host_serial} - GPU PCIe Width: {gpu_pcie_results}")
        slurm_reason("GPU PCIe Width Error")
        action = recommended_action(action, "Terminate")

    if wpa_auth_results:
        for issue in wpa_auth_results:
            logger.error(f"{host_serial} - WPA authentication issue: {issue}")
        slurm_reason("WPA Auth Error")
        action = recommended_action(action, "Reboot")

    if not fabric_manager_health:
        logger.error(f"{host_serial} - Fabric Manager not started")
        slurm_reason("Fabric Manager Error")
        action = recommended_action(action, "FabricManagerRestart")
    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')

    if  cpu_profile_issues:
        logger.error(f"CPU Profile need to be 'performance'.")
        for issue in cpu_profile_issues:
            logger.error(f" - {issue}")
        slurm_reason("CPU Profile error")
        action = recommended_action(action, "Reboot&LiveFix")

    if bad_page_issues:
        for issue in bad_page_issues:
            logger.error(f"{host_serial} - GPU has pending bad pages: {issue}")
        slurm_reason("GPU Bad page error")
        action = recommended_action(action, "Reboot")

    if len(missing_ips) > 0:
        logger.error("Missing IPs for these interfaces: "+missing_ips.join(','))
        slurm_reason("Missing IPs")
        action = recommended_action(action, "Reboot")
    logger.info(f"Finished GPU host setup check at: {datetime_str}")
    if action == "Reboot":
        logger.error("Recommended Action is to Force Reboot from the console or API")
    if action == "LiveFix":
        logger.error("Recommended Action is to Create a SR to Get the node fixed live")
    if action == "Reboot&LiveFix":
        logger.error("Recommended Action is to Create a SR to Get the node fixed live as well as force reboot the node")
    if action == "Terminate":
        logger.error("Recommended Action is to Terminate the node and Create a SR")

    if slurm_error_count > 0 and args.slurm:
        print("Healthcheck:: "+slurm_drain_reason[:-1])
        print("Healthcheck:: Recommended Action:"+action)

    http_server_file="/opt/oci-hpc/http_server/files/info"
    # Read the existing data from the file
    try:
        with open(http_server_file, 'r') as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        print("Error: File not found or not in valid JSON format.")
        exit(0)
    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    if action is None:
        data["healthcheck_recomandation"] = "Healthy"
    else:
        data["healthcheck_recomandation"] = action
    data["last_healthcheck_time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    # Read the healthcheck.log file content
    try:
        with open("/tmp/latest_healthcheck.log", 'r') as log_file:
            data["healthcheck_logs"] = log_file.read(1023)  # Store log content in JSON
    except FileNotFoundError:
        logger.warning("Log file not found, initializing empty logs.")
        data["healthcheck_logs"] = ""
    # Write updated data back to the file
    with open(http_server_file, 'w') as file:
        json.dump(data, file, indent=4)