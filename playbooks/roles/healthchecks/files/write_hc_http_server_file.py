#!/usr/bin/env python3
import sys
import argparse
import json
import requests
import logging
import subprocess

# Configure logger for write_hc_http_server_file
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('write_hc_http_server_file')

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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run multi-node NCCL active test')
    parser.add_argument("-l", "--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], default="INFO", help="Set the logging level default: INFO")
    parser.add_argument('-n', '--node1', required=True, type=str, help='node1 name')
    parser.add_argument('-m', '--node2', required=True, type=str, help='node2 name')
    parser.add_argument('-slurm', '--slurm', action='store_true', help='Add a Slurm message')

    args = parser.parse_args()
    metadata = get_metadata()
    hostname = metadata['displayName']
    logger.setLevel(args.log_level)
    node1 = args.node1
    node2 = args.node2

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
    
    result_text = ""
    # Read the latest_multi_node_active_healthcheck.log file content
    try:
        with open("/tmp/latest_multi_node_active_healthcheck.log", 'r') as log_file:
            content = log_file.read(4095)
            data["multi_node_healthcheck_logs"] = content  # Store log content in JSON
            for line in content.splitlines():
                if "result:" in line:
                    result_text = line.split(":", 1)[1].strip()
                    logger.info(f"Multi-node Healthcheck Result: {result_text}")
                    break
    except FileNotFoundError:
        logger.warning(f"{hostname}: Log file not found, initializing empty logs.")
        data["multi_node_healthcheck_logs"] = ""

    if result_text == "Healthy":
        data["multi_node_healthcheck_status"] = "Healthy"
        data["multi_node_healthcheck_recommendation"] = "Healthy"
    elif result_text == "" and (prev_multi_node_hc_status == "Potentially Bad" or prev_multi_node_hc_status == "Bad") and prev_multi_node_hc_assoc_node != multi_node_HC_associated_node:
        data["multi_node_healthcheck_status"] = "Bad"
        data["multi_node_healthcheck_recommendation"] = "Tag and Terminate"
        slurm_error = True
    elif result_text == "Potentially Bad" and (prev_multi_node_hc_status == "Potentially Bad" or prev_multi_node_hc_status == "Bad") and prev_multi_node_hc_assoc_node != multi_node_HC_associated_node:
        data["multi_node_healthcheck_status"] = "Bad"
        data["multi_node_healthcheck_recommendation"] = "Tag and Terminate"
        slurm_error = True
    elif result_text == "":
        data["multi_node_healthcheck_status"] = "Potentially Bad"
        data["multi_node_healthcheck_recommendation"] = "Run the NCCL test with another node"
    else:
        data["multi_node_healthcheck_status"] = "Potentially Bad"
        data["multi_node_healthcheck_recommendation"] = "Run the NCCL test with another node"
    logger.info(f"Data to write: {data}")
    # Write updated data back to the file
    with open(http_server_file, 'w') as file:
        try:
            json.dump(data, file, indent=4)
        except Exception as e:
            logger.error(f"Error writing to file: {e}")

    slurm_reason = "Healthcheck, active NCCL test, multi-node active NCCL test failed"
    if slurm_error and args.slurm:
        logger.info(f"{hostname}: Healthcheck:: {slurm_reason}")
        logger.info(f"{hostname}: Healthcheck:: Recommended Action: Tag and Terminate")
        cmd = [
            'sudo', 'scontrol', 'update',
            f'nodename={hostname}',
            'state=drain',
            f'reason={slurm_reason}'
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"{hostname}: Node Drain Error: {e.stderr}")