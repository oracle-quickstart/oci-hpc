#!/usr/bin/env python3
import sys
import os
import argparse
import json
import requests
import subprocess
import logging
import getpass
import time
from gpu_sdc_checker import MultiGPUSDCChecker

# Configure logger for active_healthcheck
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('active_healthcheck')


file_handler = logging.FileHandler("/tmp/latest_active_healthcheck.log", mode='w')
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
            "threshold": 185
        },
        "BM.GPU.A100-v2.8": {
            "threshold": 185
        },
        "BM.GPU4.8": {
            "threshold": 185
        },
        "BM.GPU.H100.8": {
            "threshold": 440
        },
        "BM.GPU.H200.8": {
            "threshold": 440
        },
        "BM.GPU.B200.8": {
            "threshold": 440
        }
    }
    try:
        cmd_gpu_count="nvidia-smi --query-gpu=count --format=csv,noheader"
        gpu_count=run_as_default_user(cmd_gpu_count).stdout.decode('utf-8').strip()[0]

        cmd_nccl_test="source /usr/mpi/gcc/openmpi-*/bin/mpivars.sh && /opt/oci-hpc/nccl-test/build/all_reduce_perf -b 1G -e 10G -g " + gpu_count + " -n 50 -f 2"
        result = run_as_default_user(cmd_nccl_test, timeout=120)
        if result.returncode == 0:
            output = result.stdout.decode('utf-8')
            bw=None
            for line in output.splitlines():
                if "Avg bus bandwidth" in line:
                    try:
                        bw=float(line.split()[5])
                    except:
                        logger.error(f"NCCL Test Failed: Avg bus bandwidth could not be found")
                        return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
                    if bw < shape_mapping[shape]["threshold"]:
                        logger.error(f"NCCL Test Failed: Avg bus bandwidth is {bw}")
                        return False,f"NCCL Test Failed: Avg bus bandwidth is less than {shape_mapping[shape]['threshold']}"
            if not bw is None:
                return True,"NCCL Test Succeeded: Avg bus bandwidth is "+str(bw)
            else:
                logger.error(f"NCCL Test Failed: Avg bus bandwidth could not be found")
                return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
        else:
            print(result)
            if result.stdout is None:
                if result.stderr is None:
                    output=""
                else:
                    output=result.stderr.decode('utf-8')
            else:
                output=result.stdout.decode('utf-8')
            logger.error(f"Failed to run local nccl test: {output}")
            return False, output
    except subprocess.TimeoutExpired:
        logger.error("NCCL test timed out after 2 minutes")
        output = result.stdout.decode('utf-8')
        print(output)
        return False, "Timeout after 2 minutes"
    except Exception as e:
        logger.error(f"Failed to run local nccl test: {e}")
        output = result.stdout.decode('utf-8')
        print(output)
        return False, str(e)
    
def run_local_rccl_test(shape):
    # from https://rocm.blogs.amd.com/software-tools-optimization/mi300x-rccl-xgmi/README.html
    shape_mapping = {
        "BM.GPU.MI300X.8": {
            "threshold": 310
        }
    } 
    try:
        cmd_gpu_count="rocm-smi --showproductname --json | jq 'length'"
        gpu_count=run_as_default_user(cmd_gpu_count).stdout.decode('utf-8').strip()[0]
        cmd_rccl_test="source /usr/mpi/gcc/openmpi-*/bin/mpivars.sh && /opt/rccl-tests/build/all_reduce_perf -b 1G -e 16G -f 2 -g " + gpu_count + " -n 50 -f 2"
        result = run_as_default_user(cmd_rccl_test, timeout=120)
        if result.returncode == 0:
            output = result.stdout.decode('utf-8')
            bw=None
            for line in output.splitlines():
                if "Avg bus bandwidth" in line:
                    try:
                        bw=float(line.split()[5])
                    except:
                        logger.error(f"RCCL Test Failed: Avg bus bandwidth could not be found")
                        return False,"RCCL Test Failed: Avg bus bandwidth could not be found"
                    if bw < shape_mapping[shape]["threshold"]:
                        logger.error(f"RCCL Test Failed: Avg bus bandwidth is {bw}")
                        return False,f"RCCL Test Failed: Avg bus bandwidth is less than {shape_mapping[shape]['threshold']}"
            if not bw is None:
                return True,"RCCL Test Succeeded: Avg bus bandwidth is "+str(bw)
            else:
                logger.error(f"RCCL Test Failed: Avg bus bandwidth could not be found")
                return False,"RCCL Test Failed: Avg bus bandwidth could not be found"
        else:
            print(result)
            if result.stdout is None:
                if result.stderr is None:
                    output=""
                else:
                    output=result.stderr.decode('utf-8')
            else:
                output=result.stdout.decode('utf-8')
            logger.error(f"Failed to run local Rccl test: {output}")
            return False, output
    except subprocess.TimeoutExpired:
        logger.error("RCCL test timed out after 2 minutes")
        output = result.stdout.decode('utf-8')
        print(output)
        return False, "Timeout after 2 minutes"
    except Exception as e:
        logger.error(f"Failed to run local rccl test: {e}")
        output = result.stdout.decode('utf-8')
        print(output)
        return False, str(e)

def run_gpu_fryer(run_time):
    try:
        #check if it is installed: 
        cmd_install_check="which gpu-fryer"
        install_check = run_as_default_user(cmd_install_check)
        if install_check.returncode != 0:

            cmd_install = """
                curl -sSf https://sh.rustup.rs | sh -s -- -y && \
                source "$HOME/.cargo/env" && \
                cargo install gpu-fryer
                """
            for i in range(3):
                install = run_as_default_user(cmd_install)
                if install.returncode == 0:
                    break
                else:
                    if i == 2 :
                        logger.error(f"Failed to install gpu-fryer: {install.stdout.decode('utf-8')}")
                        return False, install.stdout.decode('utf-8')
                    else:
                        time.sleep(20)
        default_user = get_default_user()
        if default_user == "opc":
            cmd_gpu_fryer = f"gpu-fryer --nvml-lib-path /lib64/libnvidia-ml.so.1 {run_time}"
        else:
            cmd_gpu_fryer = f"gpu-fryer {run_time}"
        result = run_as_default_user(cmd_gpu_fryer, timeout=run_time+20)
        if result.returncode != 0:
            logger.error(f"Failed to run gpu-fryer: {result.stdout.decode('utf-8')}")
            return False, result.stdout.decode('utf-8')
        output = result.stdout.decode('utf-8')
        if result.returncode == 0:
            for line in output.splitlines():
                if "All GPUs seem healthy" in line:
                    return True,"GPU Fryer test succeeded"
            logger.error(f"GPU Fryer failed")
            print(output)
            return False,"GPU Fryer failed"
        else:
            logger.error(f"GPU Fryer failed")
            print(output)
            return False,"GPU Fryer failed"
    except subprocess.TimeoutExpired:
        logger.error(f"GPU Fryer test timed out after {run_time+20} seconds")
        output = result.stdout.decode('utf-8')
        print(output)
        return False, f"Timeout after {run_time+20} seconds"
    except Exception as e:
        logger.error(f"Failed to run local GPU Fryer test: {e}")
        output = result.stdout.decode('utf-8')
        print(output)
        return False, str(e)

def run_gpu_sdc_check(gpu_ids=None):
    try:
        # MultiGPUSDCChecker - runs all tests on all GPUs in parallel
        checker = MultiGPUSDCChecker(gpu_ids=gpu_ids)
        logger.info(f"Running GPU SDC checks on {len(checker.checkers)} GPU(s): {list(checker.checkers.keys())}")

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
            logger.info(message)
            return True, message, summary

    except Exception as e:
        message = f"GPU SDC Test crashed: {str(e)}"
        logger.error(message)
        import traceback
        traceback.print_exc()
        return False, message, {}

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
        gpu_fryer_state,gpu_fryer_output = run_gpu_fryer(20)
        if not gpu_fryer_state:
            logger.error(f"{hostname} - GPU Fryer Test Failed: {gpu_fryer_output}")
            slurm_reason("Single node GPU Fryer Test Failed")
            action = recommended_action(action, "Tag_and_Terminate")
        else:
            logger.info(f"{hostname} - GPU Fryer Test Succeeded: {gpu_fryer_output}")

        # Run SDC checks
        sdc_state, sdc_output, sdc_details = run_gpu_sdc_check()
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
        with open("/tmp/latest_active_healthcheck.log", 'r') as log_file:
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