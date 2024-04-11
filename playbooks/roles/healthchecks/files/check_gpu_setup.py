#!/usr/bin/env python3

import subprocess
import re
import argparse
from datetime import datetime
from shared_logging import logger
from gpu_bw_test import BandwidthTest
from rdma_link_flapping import LinkFlappingTest
from xid_checker import XidChecker
import platform
import os
import requests

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
        logger.debug("User is root")
        return False
    return True

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
            logger.error(f"Oracle Cloud Agent: {version} needs to be updated to 1.38.0 or higher")
        else:
            logger.info(f"Oracle Cloud Agent: {version}")

        # Return the version
        return version

def check_rttcc_status():
    link_status = []
    devices = ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"]
    status = "disabled"
    status_dict = {"devices": {}}
    for device in devices:
        if not is_user_root():
            command = ['sudo', 'mlxreg', '-d', device, '-y', '--get', '--reg_name=PPCC', '--indexes=local_port=1,pnat=0,lp_msb=0,algo_slot=0,algo_param_index=0']
        else:
            command = ['mlxreg', '-d', device, '-y', '--set', 'cmd_type=3', '--reg_name=PPCC', '--indexes=local_port=1,pnat=0,lp_msb=0,algo_slot=0,algo_param_index=0']
        result = subprocess.run(command, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        filtered_output = [line for line in output.split('\n') if line.startswith('value')]
        for line in filtered_output:
            logger.debug(line)
            if "0x00000001" in line:
                status_dict["devices"][device] = "enabled"

    for device in status_dict["devices"]:
        if status_dict["devices"][device] == "enabled":
            logger.warning(f"RTTCC enabled on {device}")
            status = "enabled"
            link_status.append(f"RTTCC enabled on: {device}")
        else:
            logger.info(f"RTTCC status for {device}: disabled")
    if status == "disabled":
        logger.info(f"RTTCC disabled check: Passed")
    else:
        logger.error(f"RTTCC disabled check: Failed")

    return link_status

def check_ecc_errors():
    ecc_issues = []
    try:
        # Run the nvidia-smi -q command
        result = subprocess.run(['nvidia-smi', '-q'], stdout=subprocess.PIPE)
    except FileNotFoundError:
        logger.warning("Skipping SRAM/DRAM ECC Test: nvidia-smi command not found")
        return []

    # Decode the output from bytes to string
    output = result.stdout.decode('utf-8')

    # Find the lines containing "SRAM Correctable" and "DRAM Correctable"
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


    # Check if there are ecc_issues
    if len(ecc_issues) == 0:
        logger.info("GPU ECC Test: Passed")
    else:
        logger.warning("GPU ECC Test: Failed")

    return ecc_issues

def check_row_remap_errors():
    remap_issues = []
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
        if tmp_data[0] != "0":
            logger.debug(f"GPU: {i} - Row Remap Pending: {tmp_data[0]}")
            remap_issues.append(f"GPU: {i} Row Remap Pending: {tmp_data[0]}")
        if tmp_data[1] != "0":
            logger.debug(f"GPU: {i} - Row Remap Failure: {tmp_data[1]}")
            #remap_issues.append(f"GPU: {i} Row Remap Failure: {tmp_data[1]}")
        if tmp_data[2] != "0":
            logger.debug(f"GPU: {i} - Row Remap Uncorrectable: {tmp_data[2]}")
            if int(tmp_data[2]) > 512:
                remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable >512: {tmp_data[2]}")
            else:
                remap_issues.append(f"GPU: {i} - Row Remap Uncorrectable <512: {tmp_data[2]}")# Check if there are ecc_issues

    if len(remap_issues) == 0:
        logger.info("GPU Remap Test: Passed")
    else:
        logger.warning("GPU Remap Test: Failed")

    return remap_issues

def check_rdma_link_status():
    status = True
    metadata=get_metadata()
    shape=metadata['shape']
    if shape == "BM.GPU.H100.8":
        devices = ["mlx5_0", "mlx5_1", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"]
    elif shape == "BM.GPU.B4.8" or shape == "BM.GPU.A100-v2.8":
        devices = ["mlx5_1", "mlx5_2", "mlx5_3", "mlx5_4", "mlx5_5", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"]
    elif shape == "BM.GPU4.8":
        devices = ["mlx5_0", "mlx5_1", "mlx5_2", "mlx5_3", "mlx5_6", "mlx5_7", "mlx5_8", "mlx5_9", "mlx5_10", "mlx5_11", "mlx5_12", "mlx5_13", "mlx5_14", "mlx5_15", "mlx5_16", "mlx5_17"]
    link_issues = []
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
        if recommendation != "No issue was observed":
            logger.debug(f"{device}: {recommendation}")
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
    else:
        logger.info("No devices have fallen off the bus")
    if len(bus_issues) == 0:
        logger.info("Bus Check Test: Passed")
        return(bus_issues)
    else:
        logger.warning("Bus Check Test: Failed")
        return(bus_issues)

def check_gpu_count():

    lspci_expected_results = [  '0f:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '2d:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '44:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '5b:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                '89:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                'a8:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                'c0:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)',
                                'd8:00.0 3D controller: NVIDIA Corporation Device 2330 (rev a1)'
                             ]

    # Check the number of GPUs
    try:
        result = subprocess.run(['nvidia-smi', '--list-gpus'], stdout=subprocess.PIPE)
        output = result.stdout.decode('utf-8')
        lines = output.split('\n')
        tmp_results = []
        # remove empty lines
        lines = [line for line in lines if line]
        if len(lines) == 8:
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
            for line in lines:
                if line.find("NVIDIA") != -1 and line.find("2330") != -1:
                    tmp_results.append(line)
            if not len(tmp_results) == 8:
                logger.debug(f"Expected 8 GPUs, found {len(tmp_results)} in lspci output")
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

def slurm_reason(message):
    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason+=(message+"\n")
    slurm_error_count+=1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Check Host setup')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('--bw-test', dest='bw_test', action='store_true', default=False, help='Run GPU bandwidth test (default: False)')
    parser.add_argument('--bw-test-exe', dest='bw_test_exe', help='Location to cuda-sampels bandwidthTest')
    parser.add_argument('--lf-interval', dest='lf_interval', default=6, type=int, help='Link flapping interval with no flapping or link down events (default: 6 (hours))')
    parser.add_argument('-a','--all', dest='run_all', action='store_true', default=False, help='Run all checks (default: False)')
    parser.add_argument('-slurm','--slurm', dest='slurm', action='store_true', default=False, help='Add a Slurm message')
    args = parser.parse_args()

    logger.setLevel(args.log_level)

    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Started GPU host setup check at: {datetime_str}")
    try:
        oca_version = get_oca_version()
    except Exception as e:
        logger.warning(f"Failed to get Oracle Cloud Agent version with error: {e}")
        oca_version = "Unknown"
    try:
        rttcc_issues = check_rttcc_status()
    except Exception as e:
        logger.warning(f"Failed to check RTTCC status with error: {e}")
        rttcc_issues = []

    # Check for ECC errors
    try:
        ecc_issues = check_ecc_errors()
    except Exception as e:
        logger.warning(f"Failed to check ECC errors with error: {e}")
        ecc_issues = []

    # Check for row remap errors
    try:
        remap_results = check_row_remap_errors()
    except Exception as e:
        logger.warning(f"Failed to check row remap errors with error: {e}")
        remap_results = []

    # Check RDMA link status
    try:
        rdma_link_issues = check_rdma_link_status()
    except Exception as e:
        logger.warning(f"Failed to check RDMA link status with error: {e}")
        rdma_link_issues = []

    # Check for RDMA link flapping
    try:
        lft = LinkFlappingTest(time_interval=args.lf_interval)
        lft.get_rdma_link_failures()
        lft_issues = lft.process_rdma_link_flapping()
    except Exception as e:
        logger.warning(f"Failed to check RDMA link flapping with error: {e}")
        lft_issues = {"failures": [], "link_down": []}

    # Check for GPU Xid errors
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
    if len(rttcc_issues) > 0:
        logger.error(f"RTTCC issues: {rttcc_issues}")
        slurm_reason("RTTCC Error")
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
    if xid_results["status"] == "Failed":
        for xid in xid_results["results"]:
            for pci in xid_results["results"][xid]["results"]:
                logger.error(f"{host_serial} - GPU Xid {xid} device: {pci}, {xid_results['results'][xid]['description']}")
                slurm_reason("XID Error")
    if len(rdma_link_issues) > 0:
        for issue in rdma_link_issues:
            logger.error(f"{host_serial} - RDMA link issues: {issue}")
            slurm_reason("RDMA Link Error")
    if len(lft_issues["failures"]) > 0 or len(lft_issues["link_down"]) > 0:
        if len(lft_issues["failures"]) > 0:
            for issue in lft_issues["failures"]:
                logger.error(f"{host_serial} - RDMA link flapping issues: {issue}")
                slurm_reason("RDMA Link Flapping Error")
        if len(lft_issues["link_down"]) > 0:
            for issue in lft_issues["link_down"]:
                logger.error(f"{host_serial} - RDMA link down issues: {issue}")
                slurm_reason("RDMA Link Down Error")
    if bwt_results != None:
        if bwt_results["status"] == "Failed":
            for issue in bwt_results["issues"]:
                logger.error(f"{host_serial} - GPU bandwidth issues: {issue}")
                slurm_reason("GPU Bwt Error")
    if bus_results:
        logger.error(f"{host_serial} - Bus issues: {bus_results}")
        slurm_reason("GPU Bus Error")
    if gpu_results:
        logger.error(f"{host_serial} - Missing GPU(s): {gpu_results}")
        slurm_reason("Missing GPU Error")

    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Finished GPU host setup check at: {datetime_str}")

    if slurm_error_count > 0 and args.slurm:
        print("Healthcheck:: "+slurm_drain_reason[:-1])