#!/usr/bin/env python3
import sys
import argparse
import json
import requests
import logging

# Configure logger for multi_node_active_healthcheck
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('multi_node_active_healthcheck')

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
    parser.add_argument('-a', '--action', required=True, type=str, help='Slurm recommended action')
    parser.add_argument('-r', '--reason', required=True, type=str, help='Slurm drain reason')

    args = parser.parse_args()
    if not args.hostfile.strip():
        logger.error("Error: --hostfile argument cannot be empty", flush=True)
        sys.exit(1)
    metadata = get_metadata()
    shape = metadata['shape']
    hostname = metadata['displayName']
    ocid = metadata['id']
    logger.setLevel(args.log_level)
    action = args.action
    slurm_drain_reason = args.reason

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
        data["multi_node_HC_recommendation"] = "Healthy"
    else:
        data["multi_node_HC_recommendation"] = action
    data["multi_node_HC_time"] = current_time.strftime("%Y-%m-%d %H:%M:%S")
    # Read the healthcheck.log file content
    try:
        with open("/tmp/latest_multi_node_active_healthcheck.log", 'r') as log_file:
            data["multi_node_HC_logs"] = log_file.read(2047)  # Store log content in JSON
    except FileNotFoundError:
        logger.warning("Log file not found, initializing empty logs.")
        data["multi_node_HC_logs"] = ""
    if slurm_drain_reason:
        data["multi_node_HC_status"] = slurm_drain_reason
    else:
        data["multi_node_HC_status"] = "Healthy"
    # Write updated data back to the file
    with open(http_server_file, 'w') as file:
        try:
            json.dump(data, file, indent=4)
        except Exception as e:
            logger.error(f"Error writing to file: {e}")

    # pending adding associated node