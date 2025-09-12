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

file_handler = logging.FileHandler("/tmp/latest_multi_node_active_healthcheck_result.log", mode='w')
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

# # Check if the user is root
# def is_user_root():
#     if os.geteuid() != 0:
#         logger.debug("User is not root!")
#         return False
#     return True

# def get_host_serial():
#     try:
#         # Try dmidecode first (Only works on BM instances)
#         cmd = ['sudo', 'dmidecode', '-s', 'system-serial-number'] if not is_user_root() else ['dmidecode', '-s', 'system-serial-number']
#         result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         serial_number = result.stdout.decode('utf-8').strip()

#         # If dmidecode output is empty, "Not Specified", or failed, assume it's a VM
#         if result.returncode == 0 and serial_number != "Not Specified":
#             return f"BM Instance: {serial_number}"  # Bare metal instance serial number

#     except (FileNotFoundError, ValueError):
#         pass  # Continue to check for VM instance

#     try:
#         # Fallback: Get instance OCID from OCI metadata (for VM instances)
#         instance_ocid = metadata.get("id", "Unknown")
#         return f"VM Instance: {instance_ocid}"  # VM instance identifier

#     except requests.RequestException:
#         pass  # Metadata service not available

#     return "Unknown Instance"  # Final fallback if all methods fail

# def run_local_nccl_test():
#     try:
#         gpu_count=subprocess.check_output(['nvidia-smi', '--query-gpu=count', '--format=csv,noheader']).decode('utf-8').strip()[0]
#         result = subprocess.run(['/opt/oci-hpc/nccl-test/build/all_reduce_perf', '-b', '1G', '-e', '10G', '-g', gpu_count, '-n', '50', '-f', '2'], stdout=subprocess.PIPE,timeout=120)
#         if result.returncode == 0:
#             output = result.stdout.decode('utf-8')
#             bw=None
#             for line in output.splitlines():
#                 if "Avg bus bandwidth" in line:
#                     try:
#                         bw=float(line.split()[5])
#                     except:
#                         logger.error(f"NCCL Test Failed: Avg bus bandwidth could not be found")
#                         return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
#                     if bw < 200:
#                         logger.error(f"NCCL Test Failed: Avg bus bandwidth is {bw}")
#                         return False,"NCCL Test Failed: Avg bus bandwidth is less than 200"
#             if not bw is None:
#                 logger.info(f"NCCL Test Succeeded: Avg bus bandwidth is {bw}")
#                 return True,"NCCL Test Succeeded: Avg bus bandwidth is "+str(bw)
#             else:
#                 logger.error(f"NCCL Test Failed: Avg bus bandwidth could not be found")
#                 return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
#         else:
#             output = result.stdout.decode('utf-8')
#             logger.error(f"Failed to run local nccl test: {result.stderr.decode('utf-8')}")
#             return False, result.stderr.decode('utf-8')
#     except subprocess.TimeoutExpired:
#         logger.error("NCCL test timed out after 2 minutes")
#         output = result.stdout.decode('utf-8')
#         return False, "Timeout after 2 minutes"
#     except Exception as e:
#         logger.error(f"Failed to run local nccl test: {e}")
#         output = result.stdout.decode('utf-8')
#         print(output)
#         return False, str(e)
    
#DS start

def run_multi_node_nccl_test(hostfile, shape):
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

    if hostfile is None:
        logger.error(f"Multi-node NCCL Test Failed: Hostfile not passed")
        return False,"Multi-node NCCL Test Failed: Hostfile not passed"

    paths = glob.glob('/usr/mpi/gcc/openmpi-*/bin/mpivars.sh')
    if paths:
        mpivars_path = paths[0]
    else:
        logger.error(f"No mpivars.sh found")
        return False,"No mpivars.sh found"

    # # Step 3: Determine device variables
    # if shape in ("BM.GPU.B4.8", "BM.GPU.A100-v2.8"):
    #     var_UCX_NET_DEVICES = "mlx5_0:1"
    # elif shape == "BM.GPU4.8":
    #     var_UCX_NET_DEVICES = "mlx5_4:1"
    # elif shape in ("BM.GPU.H100.8", "BM.GPU.H200.8", "BM.GPU.B200.8"):
    #     var_UCX_NET_DEVICES = "eth0"
    # else:
    #     logger.error("Use the appropriate nccl test run script for non A100/H100/H200/B200 nodes")
    #     return False,"Use the appropriate nccl test run script for non A100/H100/H200/B200 nodes"

    # Set defaults
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
            executable='/bin/bash',  # Needed to use 'source'
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        # logger.info(f"Return code: {result.returncode}")
        # logger.info("dhvani1")
        # logger.error(result.stderr)
        # logger.info("dhvani2")
        logger.info(result.stdout)
        # logger.info(f"Output:", {result.stdout})
        # logger.error(f"Error:", {result.stderr})
        # if result.returncode == 0:
        #     return True, "NCCL test completed"
        # else:
        #     return False, "NCCL test failed"
        if result.returncode == 0:
            # logger.info("dhvani")
            output = result.stdout
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
                        return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
                    if bw < threshold:
                        logger.error(f"NCCL Test Failed: Avg bus bandwidth is {bw}")
                        return False,f"NCCL Test Failed: Avg bus bandwidth is less than {threshold}"
            if not bw is None:
                logger.info(f"NCCL Test Succeeded: Avg bus bandwidth is {bw}")
                return True,"NCCL Test Succeeded: Avg bus bandwidth is "+str(bw)
            else:
                logger.error(f"NCCL Test Failed: Avg bus bandwidth could not be found")
                return False,"NCCL Test Failed: Avg bus bandwidth could not be found"
        else:
            # output = result.stdout.decode('utf-8')
            logger.error(f"Failed to run multi-node nccl test: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        logger.error("NCCL test timed out after 2 minutes")
        # output = result.stdout.decode('utf-8')
        return False, "Timeout after 2 minutes"
    except Exception as e:
        logger.error(f"Failed to run multi-node nccl test: {e}")
        # output = result.stdout.decode('utf-8')
        # print(output)
        return False, str(e)
    
def custom_join(cmd_list):
    return ' '.join(('^hcoll' if x == '^hcoll' else shlex.quote(x)) for x in cmd_list)

#DS end

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
    parser = argparse.ArgumentParser(description='Run multi-node NCCL active test')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('-slurm', '--slurm', action='store_true', help='Add a Slurm message')
    parser.add_argument('-f', '--hostfile', required=True, type=str, help='Hostfile with one host per line')

    args = parser.parse_args()
    if not args.hostfile.strip():
        logger.error("Error: --hostfile argument cannot be empty", flush=True)
        sys.exit(1)
    # # Print contents of the hostfile
    # with open(args.hostfile, 'r') as f: 
    #     contents = f.read()
    #     logger.info(contents)
    metadata = get_metadata()
    shape = metadata['shape']
    hostname = metadata['displayName']
    ocid = metadata['id']
    logger.setLevel(args.log_level)
    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Started multi-node active healthcheck at: {datetime_str}")

    global slurm_drain_reason
    global slurm_error_count
    slurm_drain_reason=""
    slurm_error_count=0

    # try:
    #     host_serial = get_host_serial()
    # except Exception as e:
    #     logger.warning(f"Failed to get host serial number with error: {e}")
    #     host_serial = "Unknown"
    # logger.info(f"Node details: {hostname} - {host_serial} - {ocid} - {shape}")

    nccl_state,nccl_output = run_multi_node_nccl_test(args.hostfile, shape)
    if not nccl_state:
        logger.error(f"Multi-node NCCL Test Failed: {nccl_output}")
        slurm_reason("Multi-node NCCL Test Failed")
        action = recommended_action(action, "Tag_and_Terminate")

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

    datetime_str = datetime.now().strftime('%Y-%m-%d-%H%M%S')
    logger.info(f"Finished multi-node active healthcheck at: {datetime_str}")

    if action == None:
        action = "None"
    if slurm_drain_reason == "":
        slurm_drain_reason = "None"
        
    hc_result = {"action": action, "reason": slurm_drain_reason}
    with open('/tmp/multi_node_hc_result.json', 'w') as f:
        json.dump(hc_result, f)
    #-----

    # http_server_file="/opt/oci-hpc/http_server/files/healthchecks"
    # # Read the existing data from the file
    # try:
    #     with open(http_server_file, 'r') as file:
    #         data = json.load(file)
    # except (FileNotFoundError, json.JSONDecodeError):
    #     logger.debug("Error: File not found or not in valid JSON format.")
    #     data={}
    # current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    # if action is None:
    #     data["multi_node_active_healthcheck_recommendation"] = "Healthy"
    # else:
    #     data["multi_node_active_healthcheck_recommendation"] = action
    # data["multi_node_active_healthcheck_time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    # # Read the healthcheck.log file content
    # try:
    #     with open("/tmp/latest_multi_node_active_healthcheck.log", 'r') as log_file:
    #         data["active_healthcheck_logs"] = log_file.read(2047)  # Store log content in JSON
    # except FileNotFoundError:
    #     logger.warning("Log file not found, initializing empty logs.")
    #     data["active_healthcheck_logs"] = ""
    # if slurm_drain_reason:
    #     data["active_healthcheck_status"] = slurm_drain_reason
    # else:
    #     data["active_healthcheck_status"] = "Healthy"
    # # Write updated data back to the file
    # with open(http_server_file, 'w') as file:
    #     try:
    #         json.dump(data, file, indent=4)
    #     except Exception as e:
    #         logger.error(f"Error writing to file: {e}")