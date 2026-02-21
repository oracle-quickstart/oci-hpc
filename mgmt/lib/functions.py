from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
from concurrent.futures import ProcessPoolExecutor
from lib.ociwrap import get_host_api_dict
from lib.database import get_all_nodes, db_update_node, get_controller_node, db_get_latest_healthchecks, db_create_healthcheck, db_update_healthcheck

import subprocess
import ipaddress
from typing import List, Dict, Optional, Tuple, Set
import re
import os
import sys
import json
import time
version = sys.version_info

if version >= (3, 12):
    from datetime import datetime, timedelta, timezone, UTC
else:
    from datetime import datetime, timedelta, timezone


from lib.logger import logger

curl_timeout=3
unreachable_timeout=timedelta(hours=6)

def current_utc_time():
    if sys.version_info >= (3, 12):
        now = datetime.now(timezone.utc)
    else:
        now = datetime.utcnow()
    return now

def fetch_content(url):
    try:
        # Use subprocess to call curl
        result = subprocess.Popen(['curl', '-s', '--max-time', str(curl_timeout) ,url], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = result.communicate()  # Wait for the command to complete
        if result.returncode != 0:
            return None
        return stdout.decode('utf-8')  # Return the fetched content as a string
    except Exception as e:
        logger.error(f"Error fetching content from {url}: {e}")
        return None


def run_configure(nodes):
    logger.info(f"Restarting the configuration script on: {NodeSet(','.join([node.ip_address for node in nodes]))}")
    task = task_self()
    task.shell("sudo bash /var/lib/cloud/instance/scripts/part-001", nodes=NodeSet(','.join([node.ip_address for node in nodes])))
    task.run()
    logger.info(f"Reconfiguration is done, logs are available at /config/logs/")

def run_reset_gpus(node):
    logger.info("Resetting GPUs on: "+str(node.hostname)+" with IP "+str(node.ip_address))
    task = task_self()
    nodes = NodeSet(str(node.ip_address))
    command = "sudo /opt/oci-hpc/healthchecks/gpu_reset.sh"
    task.run(command, nodes=nodes)
    logger.info(f"GPU reset script was run. Logs are available at /var/log/healthchecks/latest_gpu_reset.log.")

def run_command(nodes,command,print_output=False):
    logger.debug(f"Running command {command} on: {NodeSet(','.join([node.ip_address for node in nodes]))}")
    task = task_self()
    task.shell(command, nodes=NodeSet(','.join([node.ip_address for node in nodes])))
    task.run()
    if print_output:
        for node in nodes:
            logger.info(f"Output from {node.hostname}: ")
            logger.info(f"{task.node_buffer(node.ip_address).decode().strip()}\n")
            logger.info(f"------------------------------------------------------------------------------------------------")
    else:
        logger.info(f"Command is done, logs are available at /config/logs/")

def run_ansible(controller_name):
    command = ". /etc/os-release; /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci/bin/ansible-playbook /config/playbooks/manage_nodes.yml"

    try:
        result = subprocess.run(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, executable="/bin/bash"
        )

        last_line=[s for s in result.stdout.split('\n') if s.startswith(controller_name)][-1]
        failure_count = int(
            [
                s for s in last_line.split(' ') if s.startswith('failed')
            ][-1].split('=')[1]
        ) + int(
            [
                s for s in last_line.split(' ') if s.startswith('unreachable')
            ][-1].split('=')[1]
        )

        if failure_count:
            print(result.stdout)
            return False
        else:
            logger.info(f"Ansible finished succesfully")
            return True
    except Exception as e:
        logger.error(f"Error running ansible: {e}")
        print(result.stdout)
        return False

def run_ansible_slurm_init(controller_name):
    command = ". /etc/os-release; /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci/bin/ansible-playbook /config/playbooks/slurm_init.yml"

    try:
        result = subprocess.run(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, executable="/bin/bash"
        )

        last_line=[s for s in result.stdout.split('\n') if s.startswith(controller_name)][-1]
        failure_count = int(
            [
                s for s in last_line.split(' ') if s.startswith('failed')
            ][-1].split('=')[1]
        ) + int(
            [
                s for s in last_line.split(' ') if s.startswith('unreachable')
            ][-1].split('=')[1]
        )

        if failure_count:
            print(result.stdout)
            return False
        else:
            logger.info(f"Ansible finished succesfully")
            return True
    except Exception as e:
        logger.error(f"Error running ansible: {e}")
        print(result.stdout)
        return False

def get_updates_based_on_url(nodes,HTTP_SERVER_PORT,filename):
    update_dict={}
    hc_update_dict={}

    if version >= (3, 12):
        current_time = datetime.now(UTC)
        time_threshold = (current_time - unreachable_timeout).replace(tzinfo=timezone.utc)
    else:
        current_time = datetime.now().astimezone(timezone.utc)
        time_threshold = (current_time - unreachable_timeout).replace(tzinfo=timezone.utc)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

    ip_addresses = [node.ip_address for node in nodes]
    urls=[f"http://{ip_address}:{HTTP_SERVER_PORT}/{filename}" for ip_address in ip_addresses]
    with ProcessPoolExecutor(max_workers=10) as executor:
        content_results = list(executor.map(fetch_content, urls))
    result_dict = dict(zip(ip_addresses, content_results))
    for node in nodes:
        update_dict[node.ocid]={}
        hc_update_dict[node.ocid]={}
        content=result_dict[node.ip_address]
        url=f"http://{node.ip_address}:{HTTP_SERVER_PORT}/{filename}"
        if content:
            try:
                if filename=="info":
                    json_data = json.loads(content)
                    json_data["last_time_reachable"]=current_time_str
                    json_data["ip_address"]=node.ip_address
                    if node.status=="starting":
                        json_data["controller_status"]="configuring"
                        json_data["status"]="running"
                    if node.status=="unreachable":
                        json_data["status"]="running"
                    if node.first_time_reachable is None:
                        json_data.update({"first_time_reachable":current_time_str})
                    logger.debug(f"Stored content for {url}")
                    update_dict[node.ocid]=json_data
                else:
                    json_data = json.loads(content)
                    hc_update_dict[node.ocid]=json_data

            except json.JSONDecodeError as e:
                if filename=="info":
                    logger.error(f"Failed to decode JSON from {url}: {e}")
                else:
                    logger.debug(f"Failed to decode JSON from {url}: {e}")
        else:
            if node.status != "starting":
                if node.last_time_reachable is None:
                    logger.info(f"Node {node.hostname} was not reachable")
                else:
                    last_time_reachable = datetime.strptime(node.last_time_reachable, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if last_time_reachable < time_threshold:
                        update_dict[node.ocid]={"status":"unreachable"}
                        logger.warning(f"Node {node.hostname} was not reachable for 6 hours")
                    else:
                        logger.error(f"Node {node.hostname} was not reachable")
            else:
                logger.warning(f"Node with {node.ip_address} is not ready yet. The webserver containing the node info is not available")

    if filename=="info":
        return update_dict
    else:
        return hc_update_dict    

def append_to_healthchecks(node_ocid, **kwargs):
    """
    Update fields for a node in the database identified by its OCID.

    Args:
        ocid (str): The OCID of the node to update.
        **kwargs: Field names and values to update.

    Example:
        db_update_node("ocid1.node.oc1..abc", status="running", controller_status="configured")
    """
    latest_healthchecks=db_get_latest_healthchecks(node_ocid)
    if "passive_healthcheck_status" in kwargs:
        passive_hc=None
        status=None
        for healthcheck in latest_healthchecks:
            if healthcheck.healthcheck_type == "passive":
                passive_hc=healthcheck
                status=healthcheck.healthcheck_status

        if passive_hc is None or (status != kwargs["passive_healthcheck_status"]):
            logger.debug(f"Creating passive healthcheck for {node_ocid}")
            db_create_healthcheck(node_ocid, {"healthcheck_last_time":kwargs["passive_healthcheck_time"],\
                                "healthcheck_type":"passive", \
                                "healthcheck_logs":kwargs["passive_healthcheck_logs"],\
                                "healthcheck_time_change":kwargs["passive_healthcheck_time"],\
                                "healthcheck_recommendation":kwargs["passive_healthcheck_recommendation"],\
                                "healthcheck_status":kwargs["passive_healthcheck_status"]})
        else:
            logger.debug(f"Updating passive healthcheck for {node_ocid}")
            db_update_healthcheck(passive_hc, {"healthcheck_last_time":kwargs["passive_healthcheck_time"],"healthcheck_logs":kwargs["passive_healthcheck_logs"]})

    if "active_healthcheck_status" in kwargs:
        active_hc=None
        status=None
        for healthcheck in latest_healthchecks:
            if healthcheck.healthcheck_type == "active":
                active_hc=healthcheck
                status=active_hc.healthcheck_status
        if active_hc is None or (status != kwargs["active_healthcheck_status"]):
            logger.debug(f"Creating active healthcheck for {node_ocid}")
            db_create_healthcheck(node_ocid, {"healthcheck_last_time":kwargs["active_healthcheck_time"],\
                                        "healthcheck_type":"active", \
                                        "healthcheck_logs":kwargs["active_healthcheck_logs"],\
                                        "healthcheck_time_change":kwargs["active_healthcheck_time"],\
                                        "healthcheck_recommendation":kwargs["active_healthcheck_recommendation"],\
                                        "healthcheck_status":kwargs["active_healthcheck_status"]})
        else:
                logger.debug(f"Updating active healthcheck for {node_ocid}")
                db_update_healthcheck(active_hc, {"healthcheck_last_time":kwargs["active_healthcheck_time"],"healthcheck_logs":kwargs["active_healthcheck_logs"]})

    if "multi_node_healthcheck_status" in kwargs:
        multi_hc=None
        multi_status=None
        for healthcheck in latest_healthchecks:
            if healthcheck.healthcheck_type == "multi-node":
                multi_hc=healthcheck
                multi_status=healthcheck.healthcheck_status
        if multi_hc is None or (multi_status != kwargs["multi_node_healthcheck_status"]):
            logger.debug(f"Creating multi-node healthcheck for {node_ocid}")
            try:
                db_create_healthcheck(node_ocid, {"healthcheck_last_time":kwargs["multi_node_healthcheck_time"],\
                                    "healthcheck_type":"multi-node", \
                                    "healthcheck_logs":kwargs["multi_node_healthcheck_logs"],\
                                    "healthcheck_time_change":kwargs["multi_node_healthcheck_time"],\
                                    "healthcheck_recommendation":kwargs["multi_node_healthcheck_recommendation"],\
                                    "healthcheck_status":kwargs["multi_node_healthcheck_status"],\
                                    "healthcheck_associated_node":kwargs["multi_node_healthcheck_associated_node"]})
            except Exception as e:
                logger.error(f"Failed to create multi-node healthcheck for {node_ocid}: {e}")
        else:
            logger.debug(f"Updating multi-node healthcheck for {node_ocid}")
            db_update_healthcheck(multi_hc, {"healthcheck_last_time":kwargs["multi_node_healthcheck_time"],"healthcheck_logs":kwargs["multi_node_healthcheck_logs"]})


def scan_host_api_logic():
    available_nodes={}
    controller = get_controller_node()
    if controller is None:
        return {}
    host_api_list = get_host_api_dict(controller.compartment_id,controller.tenancy_id)
    if not len(host_api_list):
        return {}
    node_list = get_all_nodes()
    for node in node_list:
        for host_api in host_api_list:
            if node.ocid == host_api.instance_id:
                db_update_node(node,oci_host_id=host_api.id)
                #db_update_node(node,oci_health=host_api.health,oci_impacted_components=host_api.has_impacted_components,oci_host_id=host_api.id)
    for host_api in host_api_list:
        if host_api.instance_id is None and host_api.lifecycle_state == "AVAILABLE":
            if host_api.shape in available_nodes.keys():
                available_nodes[host_api.shape]+=1
            else:
                available_nodes[host_api.shape]=1
    return available_nodes

def get_nodes_ocid_by_ip(ip_addresses,HTTP_SERVER_PORT):
    urls=[f"http://{ip_address}:{HTTP_SERVER_PORT}/info" for ip_address in ip_addresses]
    with ProcessPoolExecutor(max_workers=100) as executor:
        content_results = list(executor.map(fetch_content, urls))
    result_dict = {
        ip: content
        for ip, content in zip(ip_addresses, content_results)
        if content is not None
    }
    logger.debug(f"Result dict size: {len(result_dict.keys())}")
    ocid_dict={}
    for ip_address,content in result_dict.items():
        logger.debug(f"Handling IP {ip_address}")
        if content:
            try:
                json_data = json.loads(content)
                ocid_dict[ip_address]=json_data
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from {ip_address}")
                ocid_dict[ip_address]=None
    return ocid_dict

def get_nodes_ocid_by_subnet(subnet_cidr, HTTP_SERVER_PORT):
    """Scan a subnet and return mapping {ip: ocid} if answering."""
    network = ipaddress.ip_network(subnet_cidr, strict=False)
    ip_addresses = [str(ip) for ip in network.hosts()]
    return get_nodes_ocid_by_ip(ip_addresses,HTTP_SERVER_PORT)

def get_slurm_state():
    # Run sinfo -N -h and capture output
    if version >= (3, 12):
        current_time = datetime.now(UTC)
        time_threshold = (current_time - timedelta(minutes=10))
    else:
        current_time = datetime.now().astimezone(timezone.utc)
        time_threshold = (current_time - timedelta(minutes=10))
        
    try:
        result = subprocess.run(
            ["sinfo", "-N", "-h", "-o", "%N %R %t %i"],
            capture_output=True, text=True, check=True
        )
    except Exception as e:
        logger.error(f"Failed to run sinfo: {e}")
        return {}
    sinfo_dict = {}
    for line in result.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            node, partition, state = parts[0], parts[1], parts[2]
            if node not in sinfo_dict.keys():
                sinfo_dict[node]={}
                sinfo_dict[node]["state"]=state
                sinfo_dict[node]["partition"]=[partition]
            else:
                sinfo_dict[node]["partition"].append(partition)
            if len(parts) == 4:
                sinfo_dict[node]["reservation_id"]=parts[3]
            else:
                sinfo_dict[node]["reservation_id"]=None
    for node in sinfo_dict.keys():
        result = subprocess.run(
            ["scontrol", "show", "node", node],
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            for part in parts:
                if part.startswith("SlurmdStartTime="):
                    try:
                        start_str = part.split("=")[1]
                        start_time = datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                        sinfo_dict[node]["slurm_up_time"] = int((current_time - start_time).total_seconds())
                    except Exception as e:
                        sinfo_dict[node]["slurm_up_time"] = 0


    return sinfo_dict

def run_active_hc(node,reservation_id=None):
    partitions=node.slurm_partition.split(',')
    hc_partition=[partition for partition in partitions if 'healthcheck' in partition]
    if hc_partition:
        logger.debug(f"Submitting active healthcheck on {node.hostname} through partition {hc_partition[0]}")
        if reservation_id is None:
            cmd=["sbatch","-N","1","-p",hc_partition[0],"-w",node.hostname,"--deadline=now+8minutes","--time=00:07:00","/opt/oci-hpc/healthchecks/active_HC.sbatch"]        
        else:
            cmd=["sbatch","-N","1","-p",hc_partition[0],"-w",node.hostname,"--reservation",reservation_id,"--deadline=now+8minutes","--time=00:07:00","/opt/oci-hpc/healthchecks/active_HC.sbatch"]
        logger.debug(f"Running command: {' '.join(cmd)}")
        results = subprocess.run(cmd)
        if results.returncode != 0:
            logger.debug("Slurm launch failed, trying to reconfiguring Slurm before retrying")
            reconfigure=subprocess.run(["sudo","scontrol","reconfigure"])
            logger.debug(f"Running command: {' '.join(cmd)}")
            results2 = subprocess.run(cmd)
            if results2.returncode != 0:
                logger.warning(f"Slurm launch failed after reconfiguring Slurm")
                logger.warning(f"Error message: {results2.stderr}")
            else:
                logger.debug(f"Slurm Job launch successful after reconfiguring Slurm")
    else:
        logger.warning(f"No healthcheck partition found for {node.hostname}")

def run_multi_node_active_hc(nodes,exclude_node=None,reservation_id=None):
    if len(nodes)==1:
        node=nodes[0]
        hostnames=node.hostname
        partitions=node.slurm_partition.split(',')
        hc_partition=[partition for partition in partitions if 'healthcheck' in partition]
    elif len(nodes)==2:
        node_1=nodes[0]
        node_2=nodes[1]
        hostnames=node_1.hostname+','+node_2.hostname
        partitions_1=node_1.slurm_partition.split(',')
        partitions_2=node_2.slurm_partition.split(',')
        hc_partition_1=[partition for partition in partitions_1 if 'healthcheck' in partition]
        hc_partition_2=[partition for partition in partitions_2 if 'healthcheck' in partition]
        hc_partition=list(set(hc_partition_1) & set(hc_partition_2))
    else:
        logger.error("The number of nodes does not make sense")
    if hc_partition:
        logger.info(f"Submitting multi node healthcheck on {hostnames} through partition {hc_partition[0]}")
        healthcheck_script="/opt/oci-hpc/healthchecks/multi_node_active_HC.sbatch"
        try:
            gpu_count = str(int(node_1.shape.split(".")[-1]))
        except:
            gpu_count = str(8)
        if exclude_node is None:
            if reservation_id is None:
                cmd=["sbatch","-N","2","-p",hc_partition[0],"--ntasks-per-node",gpu_count,"--gpus-per-node",gpu_count,"-w",hostnames,"--deadline=now+5minutes","--time=4:00",healthcheck_script]       
            else:
                cmd=["sbatch","-N","2","-p",hc_partition[0],"--ntasks-per-node",gpu_count,"--gpus-per-node",gpu_count,"-w",hostnames,"--reservation",reservation_id,"--deadline=now+5minutes","--time=00:04:00",healthcheck_script] 
        else:
            if reservation_id is None:
                cmd=["sbatch","-N","2","-p",hc_partition[0],"--ntasks-per-node",gpu_count,"--gpus-per-node",gpu_count,"-w",hostnames,"-x",exclude_node,"--deadline=now+5minutes","--time=00:04:00",healthcheck_script] 
            else:
                cmd=["sbatch","-N","2","-p",hc_partition[0],"--ntasks-per-node",gpu_count,"--gpus-per-node",gpu_count,"-w",hostnames,"-x",exclude_node,"--reservation",reservation_id,"--deadline=now+5minutes","--time=00:04:00",healthcheck_script] 
        logger.debug(f"Running command: {' '.join(cmd)}")
        results = subprocess.run(cmd)
        if results.returncode != 0:
            logger.debug("Slurm launch failed, trying to reconfiguring Slurm before retrying")
            reconfigure=subprocess.run(["sudo","scontrol","reconfigure"])
            logger.debug(f"Running command: {' '.join(cmd)}")
            results2 = subprocess.run(cmd)
            if results2.returncode != 0:
                logger.warning(f"Slurm launch failed after reconfiguring Slurm")
                logger.warning(f"Error message: {results2.stderr}")
            else:
                logger.debug(f"Slurm Job launch successful after reconfiguring Slurm")
    else:
        logger.warning(f"No healthcheck partition found for {hostnames}")

def get_ansiblevars(inventory_path,ansiblevars):
    parser = configparser.ConfigParser(allow_no_value=True, delimiters=('='))
    parser.optionxform = str  # preserve case (important for ansible vars)

    # Prepend a dummy section header if needed
    with open(inventory_path) as f:
        content = f.read()

    # configparser requires all keys to be under a section,
    # so we wrap the inventory in a dummy section if not already.
    if not content.strip().startswith('['):
        content = '[inventory]\n' + content

    parser.read_string(content)

    output={}
    # Retrieve the private_subnet value from [all:vars]
    for ansiblevar in ansiblevars:
        try:
            output[ansiblevar] = parser['all:vars'][ansiblevar]
        except KeyError:
            KeyError("Could not find 'private_subnet' in [all:vars]")
    return output

def remove_reservation(nodes):
    if len(nodes)>0:
        updated_reservation=subprocess.run(["sudo","scontrol","update","reservation","reservation=InitialValidation","Nodes-="+','.join([node.hostname for node in nodes])], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if updated_reservation.returncode != 0:
            for node in nodes:
                try:
                    updated_reservation_individual=subprocess.run(["sudo","scontrol","update","reservation","reservation=InitialValidation","Nodes-="+node.hostname], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                except Exception as e:
                    logger.error(f"Failed to remove reservation for {node.hostname}: {e}")
                if updated_reservation_individual.returncode != 0:
                    res_check=subprocess.run(["sudo","scontrol","show","reservation","InitialValidation"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    time.sleep(1)
                    for i in res_check.stdout.decode('utf-8').split():
                        if "Nodes=" in i:
                            nodes_in_reservation=i.split("=")[1].split(",")
                            if len(nodes_in_reservation)==1:
                                subprocess.run(["sudo","scontrol","delete","reservation","InitialValidation"])
                            else:
                                logger.error(f"Failed to remove reservation for {node.hostname}: {e}")                
    else:
        logger.debug("No nodes found to remove reservation")

def get_node_configuration(config) -> Dict[str, any]:
    """
    Get node configuration parameters based on shape.
    Returns a dictionary with Boards, SocketsPerBoard, CoresPerSocket, ThreadsPerCore, and optional Gres.
    """
    
    # Base configuration lookup table
    threadspercore = 1
    if config.hyperthreading:
        threadspercore = 2
    configs = {
        "BM.GPU2.2": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 14, 
            "ThreadsPerCore": threadspercore, "Gres": "gpu:P100:2"
        },
        "VM.GPU2.1": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 12,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:P100:1"
        },
        "VM.GPU3.1": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 6,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:V100:1"
        },
        "VM.GPU3.2": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 12,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:V100:2"
        },
        "VM.GPU3.4": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 24,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:V100:4"
        },
        "BM.GPU3.8": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 26,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:V100:8"
        },
        "BM.GPU4.8": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 32,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:A100:8"
        },
        "BM.GPU.H100.8": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 56,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:H100:8"
        },
        "BM.GPU.T1.2": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 32,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:A10:2"
        },
        "BM.GPU.A10.4": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 32,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:A10:4"
        },
        "VM.GPU.A10.2": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 30,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:A10:2"
        },
        "VM.GPU.A10.1": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 15,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:A10:1"
        },
        "BM.HPC2.36": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 18,
            "ThreadsPerCore": threadspercore
        },
        "BM.HPC.E5.144": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 72,
            "ThreadsPerCore": threadspercore
        },
        "BM.Standard.E5.192": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 96,
            "ThreadsPerCore": threadspercore
        },
        "BM.Optimized3.36": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 18,
            "ThreadsPerCore": threadspercore
        },
        "BM.Standard2.52": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 26,
            "ThreadsPerCore": threadspercore
        },
        "BM.Standard3.64": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 32,
            "ThreadsPerCore": threadspercore
        },
        "BM.Standard.E2.64": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 32,
            "ThreadsPerCore": threadspercore
        },
        "BM.Standard.A1.160": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 80,
            "ThreadsPerCore": 1
        },
        "BM.DenseIO.E5.128": {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 64,
            "ThreadsPerCore": threadspercore
        },
        "VM.Standard.A1.Flex": {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": None,  # Set dynamically
            "ThreadsPerCore": 1
        },
    }
    # Shapes with threadspercore-specific configurations
    threadspercore_specific = {
        ("BM.GPU.B4.8", 1): {
            "Boards": 1, "SocketsPerBoard": 8, "CoresPerSocket": 16,
            "ThreadsPerCore": 1, "Gres": "gpu:A100:8"
        },
        ("BM.GPU.B4.8", 2): {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 255,
            "ThreadsPerCore": 1, "Gres": "gpu:A100:8"
        },
        ("BM.GPU.A100-v2.8", 1): {
            "Boards": 1, "SocketsPerBoard": 8, "CoresPerSocket": 16,
            "ThreadsPerCore": 1, "Gres": "gpu:A100:8"
        },
        ("BM.GPU.A100-v2.8", 2): {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 255,
            "ThreadsPerCore": 1, "Gres": "gpu:A100:8"
        },
        ("BM.GPU.H200.8", 2): {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 56,
            "ThreadsPerCore": threadspercore, "Gres": "gpu:H200:8"
        },
        ("BM.Standard.E3.128", 1): {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 64,
            "ThreadsPerCore": threadspercore
        },
        ("BM.Standard.E3.128", 2): {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 255,
            "ThreadsPerCore": 1
        },
        ("BM.Standard.E4.128", 1): {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 64,
            "ThreadsPerCore": threadspercore
        },
        ("BM.Standard.E4.128", 2): {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 255,
            "ThreadsPerCore": 1
        },
        ("BM.DenseIO.E4.128", 1): {
            "Boards": 1, "SocketsPerBoard": 2, "CoresPerSocket": 64,
            "ThreadsPerCore": threadspercore
        },
        ("BM.DenseIO.E4.128", 2): {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": 255,
            "ThreadsPerCore": 1
        },
    }
    
    # Flex shapes (dynamic cores)
    flex_shapes = [
        "VM.Standard.E3.Flex", "VM.Standard.E4.Flex", "VM.Standard.E5.Flex",
        "VM.Standard.E6.Flex", "VM.Optimized3.Flex", "VM.Standard3.Flex",
        "VM.DenseIO.E4.Flex", "VM.DenseIO.E5.Flex"
    ]
    
    # Check threadspercore-specific first
    if (config.shape, threadspercore) in threadspercore_specific:
        return threadspercore_specific[(config.shape, threadspercore)]
    
    # Check standard configs
    if config.shape in configs:
        return configs[config.shape]
    
    # Check flex shapes
    if config.shape in flex_shapes:
        return {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": None,
            "ThreadsPerCore": threadspercore
        }
    
    # Handle VM.Standard2.X pattern
    if "VM.Standard2." in config.shape:
        cores = int(config.shape.split('.')[-1])
        return {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": cores,
            "ThreadsPerCore": threadspercore
        }
    
    # Handle VM.Standard.E2.X pattern
    if "VM.Standard.E2." in config.shape:
        cores = int(config.shape.split('.')[-1])
        return {
            "Boards": 1, "SocketsPerBoard": 1, "CoresPerSocket": cores,
            "ThreadsPerCore": threadspercore
        }
    
    return None

def generate_nodename_entry(config) -> Optional[str]:
    """
    Generate NodeName entry for slurm.conf based on instance configuration.
    
    Args:
        config: Configuration object with attributes: shape, hostname_convention, 
                 max_number_nodes, name, instance_pool_ocpus (for Flex shapes)
        threadspercore: Number of threads per core
    
    Returns:
        String with NodeName configuration or None if shape not recognized
    """
    slurm_entry = get_node_configuration(config)
    
    if slurm_entry is None:
        logger.warning(f"Unknown shape: {config.shape}")
        return None
    
    # Handle dynamic CoresPerSocket for Flex shapes
    cores_per_socket = slurm_entry["CoresPerSocket"]
    if cores_per_socket is None:
        cores_per_socket = config.instance_pool_ocpus
    
    # Build the NodeName entry
    parts = [
        f"NodeName={config.hostname_convention}-[1-{config.max_number_nodes}]",
        f"Boards={slurm_entry['Boards']}",
        f"SocketsPerBoard={slurm_entry['SocketsPerBoard']}",
        f"CoresPerSocket={cores_per_socket}",
        f"ThreadsPerCore={slurm_entry['ThreadsPerCore']}",
        "State=CLOUD",
        f"Feature={config.name}"
    ]
    
    # Add Gres if present
    if "Gres" in slurm_entry:
        parts.append(f"Gres={slurm_entry['Gres']}")
    
    return " ".join(parts)

def generate_slurm_entries(configs) -> Tuple[List[str], Dict]:
    """Generate Nodeset, NodeName and PartitionName entries from database configs."""
    entries = []
    partitions_permanent = {}
    partitions_ondemand = {}

    for config in configs:
        if config.permanent:
            entries.append(f"Nodeset={config.name} Feature={config.name}")
            if config.partition in partitions_permanent:
                partitions_permanent[config.partition]["names"].append(config.name)
            else:
                partitions_permanent[config.partition] = {
                    "names": [config.name],
                    "default": "NO"
                }
            if config.default_partition:
                partitions_permanent[config.partition]["default"] = "YES"
        else:
            if config.stand_alone:
                nodename_entry = generate_nodename_entry(config)
                if nodename_entry:
                    entries.append(nodename_entry)
                    if config.partition in partitions_ondemand:
                        partitions_ondemand[config.partition]["nodes"].append(
                            f"{config.hostname_convention}-[1-{config.max_number_nodes}]"
                        )
                    else:
                        partitions_ondemand[config.partition] = {
                            "nodes": [f"{config.hostname_convention}-[1-{config.max_number_nodes}]"],
                            "default": "NO"
                        }
            else:
                logger.warning(
                    f"On demand partition detected but Standalone was not {str(config.stand_alone)}. "
                    f"Standalone must be true for On Demand. Review configuration {config.name}"
                )
                logger.warning(f"Ignoring {config.name}")

    # Generate permanent partition entries
    for partition_name, partition_data in partitions_permanent.items():
        nodes = ",".join(partition_data["names"])
        default = partition_data["default"]
        entries.append(f"PartitionName={partition_name} Nodes={nodes} Default={default}")

        # Generate a healthcheck partition for each nodeset in this partition
        for nodeset_name in partition_data["names"]:
            entries.append(
                f"PartitionName={nodeset_name}-healthcheck Nodes={nodeset_name} Default=NO PriorityTier=0"
            )

    # Generate on-demand partition entries
    for partition_name, partition_data in partitions_ondemand.items():
        nodes = ",".join(partition_data["nodes"])
        default = partition_data["default"]
        entries.append(
            f"PartitionName={partition_name} Nodes={nodes} Default={default} "
            f"ResumeTimeout=1200 SuspendTimeout=200 SuspendTime=300"
        )

    return entries, partitions_ondemand

def read_slurm_conf(filepath='/etc/slurm/slurm.conf'):
    """Read slurm.conf and separate managed and unmanaged lines."""
    managed_keywords = ["Nodeset", "NodeName", "PartitionName"]

    # We no longer ignore healthcheck partitions - they are now fully managed
    # Only ignore lines that are truly not managed by this script
    ignored_lines = []

    unmanaged_lines = []
    existing_managed_lines = []

    with open(filepath, 'r') as f:
        for line in f:
            stripped = line.rstrip('\n')

            # Keep truly unmanaged lines
            if stripped.strip() in ignored_lines:
                unmanaged_lines.append(stripped)
                continue

            # Check if it's a managed line
            if any(stripped.strip().startswith(kw) for kw in managed_keywords):
                existing_managed_lines.append(stripped.strip())
                continue

            # Keep all other lines
            unmanaged_lines.append(stripped)

    return unmanaged_lines, existing_managed_lines

def write_slurm_conf(unmanaged_lines, managed_entries, filepath='/etc/slurm/slurm.conf', backup=True):
    """Write updated slurm.conf with managed entries."""
    
    # Create backup
    if backup and os.path.exists(filepath):
        backup_path = f"{filepath}.backup"
        subprocess.run(['cp', filepath, backup_path], check=True)
        logger.info(f"Created backup at {backup_path}")
    
    # Remove the auto-generated comment if it already exists in unmanaged lines
    marker_comment = '# Auto-generated entries from database'
    unmanaged_lines = [line for line in unmanaged_lines if line.strip() != marker_comment.strip()]
    
    # Remove trailing empty lines from unmanaged content
    while unmanaged_lines and not unmanaged_lines[-1].strip():
        unmanaged_lines.pop()
    
    with open(filepath, 'w') as f:
        # Write unmanaged lines first
        for line in unmanaged_lines:
            f.write(line + '\n')
        
        # Add a separator comment (only once)
        f.write('\n' + marker_comment + '\n')
        
        # Write managed entries
        for entry in managed_entries:
            f.write(entry + '\n')

def check_root_privileges():
    """Check if the script is running as root and warn if not."""
    if os.geteuid() != 0:
        logger.warning("This script is not running as root")
        logger.warning("Modifying files in /etc typically requires root privileges")
        logger.warning("You may encounter permission errors")
        
        response = input("\nDo you want to continue anyway? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            logger.info("Operation cancelled by user")
            return False
    return True

def get_active_nodes_from_partition(partition_name: str) -> Set[str]:
    """
    Get list of active nodes in a partition using sinfo.
    
    Args:
        partition_name: Name of the partition
    
    Returns:
        Set of active node names
    """
    try:
        result = subprocess.run(
            ['sinfo', '-h', '-p', partition_name, '-N', '-o', "'%N %T'"],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"Failed to query nodes for partition {partition_name}")
            return set()
        
        active_nodes = set()
        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                node_name = parts[0]
                state = parts[1]
                # Consider nodes as active if they're not in idle~ or down state
                if 'idle~' not in state.lower() and 'down' not in state.lower():
                    active_nodes.add(node_name)
        
        return active_nodes
        
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout querying nodes for partition {partition_name}")
        return set()
    except Exception as e:
        logger.warning(f"Error querying nodes for partition {partition_name}: {e}")
        return set()

def check_hostname_has_active_nodes(hostname_prefix: str, node_range: str, active_nodes: Set[str]) -> bool:
    """
    Check if any nodes with the given hostname prefix are active.
    
    Args:
        hostname_prefix: Hostname prefix like "GPU-OD-"
        node_range: Full node range like "GPU-OD-[1-100]"
        active_nodes: Set of currently active node names
    
    Returns:
        True if any nodes are active, False otherwise
    """
    # Extract all possible nodes from the range
    try:
        nodeset = NodeSet(node_range)
        for node in nodeset:
            if node in active_nodes:
                return True
        return False
    except Exception as e:
        logger.warning(f"Error parsing node range {node_range}: {e}")
        return False
def check_topology_line_fragmentation(topology_line: str, hostname_prefix: str) -> int:
    """
    Count how many times a hostname prefix appears in a topology line.
    If count > 1, it means nodes are fragmented (some are active).
    
    Args:
        topology_line: Topology line like "SwitchName=partition:inactive Nodes=GPU-OD-[1-3],GPU-OD-[5-100]"
        hostname_prefix: Hostname prefix like "GPU-OD-"
    
    Returns:
        Count of occurrences of the hostname prefix
    """
    try:
        # Extract the Nodes= part
        if 'Nodes=' not in topology_line:
            return 0
        
        nodes_part = topology_line.split('Nodes=')[1].strip()
        
        # Split by comma and count occurrences of hostname prefix
        mylist = [x.split("[") for x in nodes_part.split(",")]
        mylist2 = [y for x in mylist for y in x]
        count = mylist2.count(hostname_prefix)
        
        return count
    except Exception as e:
        logger.warning(f"Error parsing topology line: {e}")
        return 0


def read_topology_conf_advanced(filepath='/etc/slurm/topology.conf'):
    """
    Read topology.conf and parse managed entries by partition.
    All lines related to managed partitions (with :inactive) are excluded from unmanaged_lines.
    
    Returns:
        Tuple of (unmanaged_lines, managed_partitions) where managed_partitions is a dict
        mapping partition names to their node ranges
    """
    ignored_lines = [
        "SwitchName=initial_startup_bugfix Nodes=non_existent_node"
    ]
    
    unmanaged_lines = []
    managed_partitions = {}
    marker_comment = '# Auto-generated on-demand node topology'
    in_managed_section = False
    managed_partition_names = set()

    if not os.path.exists(filepath):
        logger.warning(f"Topology file not found: {filepath}")
        return unmanaged_lines, managed_partitions
    
    # First pass: identify all managed partitions
    with open(filepath, 'r') as f:
        for line in f:
            stripped = line.strip()
            if marker_comment in stripped:
                in_managed_section = True
                continue
            
            if in_managed_section or ':inactive' in stripped:
                # Extract partition name from managed entries
                match = re.match(r'SwitchName=([^:]+):inactive', stripped)
                if match:
                    managed_partition_names.add(match.group(1))
    
    # Second pass: separate managed from unmanaged lines
    in_managed_section = False
    with open(filepath, 'r') as f:
        for line in f:
            stripped = line.rstrip('\n')
            stripped_no_space = stripped.strip()
            
            # Skip marker comment
            if stripped_no_space == marker_comment.strip():
                in_managed_section = True
                continue
            
            # Keep ignored lines
            if stripped_no_space in ignored_lines:
                unmanaged_lines.append(stripped)
                continue
            
            # Skip everything in managed section
            if in_managed_section:
                # Parse managed entries
                if 'Nodes=' in stripped_no_space and ':inactive' in stripped_no_space:
                    match = re.match(r'SwitchName=([^:]+):inactive\s+Nodes=(.+)', stripped_no_space)
                    if match:
                        partition = match.group(1)
                        nodes = match.group(2).strip()
                        if partition not in managed_partitions:
                            managed_partitions[partition] = {"nodes": nodes}
                continue
            
            # Check if this line is related to any managed partition
            is_managed = False
            for partition in managed_partition_names:
                if (f'{partition}:inactive' in stripped_no_space or 
                    f'SwitchName={partition} Switches={partition}:inactive' == stripped_no_space):
                    is_managed = True
                    # Parse nodes from managed entries outside marker section
                    if 'Nodes=' in stripped_no_space and ':inactive' in stripped_no_space:
                        match = re.search(r'Nodes=(.+)', stripped_no_space)
                        if match:
                            nodes = match.group(1).strip()
                            if partition not in managed_partitions:
                                managed_partitions[partition] = {"nodes": nodes}
                    break
            
            if is_managed:
                continue
            
            # Unmanaged line
            unmanaged_lines.append(stripped)
    
    return unmanaged_lines, managed_partitions

def generate_topology_entries_simple(partitions_ondemand: Dict[str, Dict]) -> Tuple[List[str], bool]:
    """
    Generate topology.conf entries for on-demand partitions.
    
    Args:
        partitions_ondemand: Dict like {"partition": {"nodes": ["GPU-OD-[1-100]"], "default": "NO"}}
    
    Returns:
        Tuple of (topology_entries, has_changes) where has_changes indicates if we should abort
    """
    if not partitions_ondemand:
        return [], False
    
    entries = []
    
    # Read existing topology to check for fragmentation
    _, existing_managed = read_topology_conf_advanced()
    
    # Check each partition
    for partition in partitions_ondemand:
        # Get active nodes for this partition
        active_nodes = get_active_nodes_from_partition(partition)
        
        # Combine all node ranges for this partition
        all_node_ranges = partitions_ondemand[partition]["nodes"]
        
        # Check each hostname convention in this partition
        abort_changes = False
        for node_range in all_node_ranges:
            # Extract hostname prefix (e.g., "GPU-OD-" from "GPU-OD-[1-100]")
            match = re.match(r'([A-Za-z0-9_-]+)-\[', node_range)
            if match:
                hostname_prefix = match.group(1) + "-"
                
                # Check if this hostname has active nodes
                if check_hostname_has_active_nodes(hostname_prefix, node_range, active_nodes):
                    # Check if existing topology has fragmentation
                    if partition in existing_managed:
                        existing_line = f"SwitchName={partition}:inactive Nodes={existing_managed[partition]['nodes']}"
                        fragmentation_count = check_topology_line_fragmentation(existing_line, hostname_prefix)
                        
                        if fragmentation_count > 1:
                            logger.error(f"Cannot update topology for partition '{partition}'")
                            logger.error(f"Hostname '{hostname_prefix}' has active nodes and existing topology is fragmented")
                            logger.error(f"Existing topology: {existing_managed[partition]['nodes']}")
                            logger.error(f"This indicates nodes are currently running. Aborting changes.")
                            abort_changes = True
                            break
        
        if abort_changes:
            return [], True
        
        # Generate entries for this partition
        # Combine all node ranges into a single line
        nodes_combined = ",".join(all_node_ranges)
        entries.append(f"SwitchName={partition}:inactive Nodes={nodes_combined}")
        entries.append(f"SwitchName={partition} Switches={partition}:inactive")
    
    return entries, False


def read_topology_conf(filepath='/etc/slurm/topology.conf'):
    """
    Read topology.conf and separate managed and unmanaged entries.
    Managed entries are auto-generated on-demand node topology entries.
    """
    ignored_lines = [
        "SwitchName=initial_startup_bugfix Nodes=non_existent_node"
    ]
    
    unmanaged_lines = []
    existing_managed_nodes = set()  # Track which partitions have managed entries
    marker_comment = '# Auto-generated inactive node topology'
    in_managed_section = False

    if not os.path.exists(filepath):
        logger.warning(f"Topology file not found: {filepath}")
        return unmanaged_lines, existing_managed_nodes
    
    with open(filepath, 'r') as f:
        for line in f:
            stripped = line.rstrip('\n')
            
            # Check for marker comment
            if stripped.strip() == marker_comment.strip():
                in_managed_section = True
                continue
           # Keep ignored lines
            if stripped.strip() in ignored_lines:
                unmanaged_lines.append(stripped)
                continue            
            # Skip managed entries (those in the auto-generated section with :inactive)

            if in_managed_section and ':inactive' in stripped:
                # Extract node ranges from managed entries to track them
                if 'Nodes=' in stripped:
                    match = re.search(r'Nodes=([^\s]+)', stripped)
                    if match:
                        existing_managed_nodes.add(match.group(1))
                continue
            # Keep all other lines
            # If we hit a non-managed, non-empty line after managed section, we're done with managed section
            if in_managed_section and stripped.strip() and ':inactive' not in stripped:
                in_managed_section = False
            
            # Skip empty lines at the end of managed section
            if in_managed_section and not stripped.strip():
                continue
            
            # Keep all other lines (active nodes, other switches, etc.)
            unmanaged_lines.append(stripped)
    
    return unmanaged_lines, existing_managed_nodes



def write_topology_conf(unmanaged_lines, managed_entries, filepath='/etc/slurm/topology.conf', backup=True):
    """Write updated topology.conf with managed entries."""
    
    # Create backup
    if backup and os.path.exists(filepath):
        backup_path = f"{filepath}.backup"
        subprocess.run(['cp', filepath, backup_path], check=True)
        logger.info(f"Created topology backup at {backup_path}")
    
    # Remove the auto-generated comment if it exists
    marker_comment = '# Auto-generated on-demand node topology'
    unmanaged_lines = [line for line in unmanaged_lines if line.strip() != marker_comment.strip()]
    
    # Remove trailing empty lines
    while unmanaged_lines and not unmanaged_lines[-1].strip():
        unmanaged_lines.pop()
    
    with open(filepath, 'w') as f:
        # Write unmanaged lines first
        for line in unmanaged_lines:
            f.write(line + '\n')
        
        # Add managed entries if any
        if managed_entries:
            f.write('\n' + marker_comment + '\n')
            for entry in managed_entries:
                f.write(entry + '\n')

def sync_slurm_config(configs, slurm_conf_path='/etc/slurm/slurm.conf', 
                     topology_conf_path='/etc/slurm/topology.conf'):
    """Synchronize database configs with slurm.conf and topology.conf."""
    backup_path = f"{slurm_conf_path}.backup"
    topology_backup_path = f"{topology_conf_path}.backup"
    
    # Check if modifying a file in /etc and warn if not root
    if slurm_conf_path.startswith('/etc/') and not check_root_privileges():
        return False
    
    try:
        # Generate entries for both files
        new_slurm_entries, partitions_ondemand = generate_slurm_entries(configs)
        
        # Read existing configurations
        unmanaged_slurm, existing_slurm = read_slurm_conf(slurm_conf_path)
        
        # Check for changes in slurm.conf
        new_slurm_set = set(new_slurm_entries)
        existing_slurm_set = set(existing_slurm)
        slurm_changed = new_slurm_set != existing_slurm_set
        
        # Show changes for slurm.conf
        if slurm_changed:
            added_slurm = new_slurm_set - existing_slurm_set
            removed_slurm = existing_slurm_set - new_slurm_set
            
            if added_slurm:
                logger.info("Slurm.conf - Adding entries:")
                for entry in added_slurm:
                    logger.info(f"  + {entry}")
            
            if removed_slurm:
                logger.info("Slurm.conf - Removing entries:")
                for entry in removed_slurm:
                    logger.info(f"  - {entry}")
            
            # Write updated slurm.conf
            write_slurm_conf(unmanaged_slurm, new_slurm_entries, slurm_conf_path, backup=True)
            
            # Reconfigure slurmctld to pick up slurm.conf changes
            logger.info("Reconfiguring slurmctld after slurm.conf update...")
            result = subprocess.run(['scontrol', 'reconfigure'], 
                                   capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"scontrol reconfigure failed: {result.stderr}")
                rollback_config(slurm_conf_path, backup_path)
                return False
        
        # Generate topology entries and check for conflicts
        new_topology_entries, should_abort = generate_topology_entries_simple(partitions_ondemand)
        
        if should_abort:
            logger.error("Aborting topology changes due to active nodes")
            if slurm_changed:
                logger.warning("Slurm.conf was updated but topology.conf was not changed")
            return False
        
        # Read existing topology
        unmanaged_topology, existing_managed_partitions = read_topology_conf_advanced()
        
        # Check for topology changes
        new_topology_set = set(new_topology_entries)
        existing_topology_lines = []
        for partition, data in existing_managed_partitions.items():
            existing_topology_lines.append(f"SwitchName={partition}:inactive Nodes={data['nodes']}")
            existing_topology_lines.append(f"SwitchName={partition} Switches={partition}:inactive")
        existing_topology_set = set(existing_topology_lines)
        
        topology_changed = new_topology_set != existing_topology_set
        
        if topology_changed:
            logger.info("Topology.conf - Changes detected:")
            
            # Show what's changing
            new_partitions = set(partitions_ondemand.keys())
            old_partitions = set(existing_managed_partitions.keys())
            
            added_partitions = new_partitions - old_partitions
            removed_partitions = old_partitions - new_partitions
            modified_partitions = new_partitions & old_partitions
            
            if added_partitions:
                logger.info("  Adding new partitions:")
                for p in added_partitions:
                    logger.info(f"    + {p}")
            
            if removed_partitions:
                logger.info("  Removing partitions:")
                for p in removed_partitions:
                    logger.info(f"    - {p}")
            
            if modified_partitions:
                logger.info("  Modifying partitions:")
                for p in modified_partitions:
                    old_nodes = existing_managed_partitions[p]['nodes']
                    new_nodes = ",".join(partitions_ondemand[p]['nodes'])
                    if old_nodes != new_nodes:
                        logger.info(f"    {p}:")
                        logger.info(f"      Old: {old_nodes}")
                        logger.info(f"      New: {new_nodes}")
            
            # Write updated topology
            write_topology_conf(unmanaged_topology, new_topology_entries, 
                              topology_conf_path, backup=True)
            
            # Reconfigure slurmctld
            logger.info("Reconfiguring slurmctld after topology.conf update...")
            result = subprocess.run(['scontrol', 'reconfigure'], 
                                   capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"scontrol reconfigure failed: {result.stderr}")
                rollback_config(topology_conf_path, topology_backup_path)
                return False
        
        if not slurm_changed and not topology_changed:
            logger.info("No changes detected in slurm.conf or topology.conf - skipping update")
            return True
        
        logger.info("✓ Successfully synchronized configurations and reconfigured slurmctld")
        return True
            
    except subprocess.TimeoutExpired:
        logger.error("scontrol reconfigure timed out")
        if slurm_changed and os.path.exists(backup_path):
            rollback_config(slurm_conf_path, backup_path)
        if 'topology_changed' in locals() and topology_changed and os.path.exists(topology_backup_path):
            rollback_config(topology_conf_path, topology_backup_path)
        return False
    except PermissionError as e:
        logger.error(f"Permission denied - {e}")
        logger.error("This operation requires root privileges")
        logger.error("Please run with: sudo python manage.py configurations sync-config")
        return False
    except Exception as e:
        logger.error(f"Error synchronizing slurm config: {e}")
        if os.path.exists(backup_path):
            rollback_config(slurm_conf_path, backup_path)
        if os.path.exists(topology_backup_path):
            rollback_config(topology_conf_path, topology_backup_path)
        return False

def rollback_config(slurm_conf_path, backup_path):
    """Rollback slurm.conf to backup and reconfigure slurmctld."""
    try:
        logger.warning("="*60)
        logger.warning("ROLLBACK: Reverting to previous configuration")
        logger.warning("="*60)
        
        if not os.path.exists(backup_path):
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        # Restore backup
        logger.info(f"Restoring backup from: {backup_path}")
        subprocess.run(['cp', backup_path, slurm_conf_path], check=True)
        
        # Reconfigure with old config
        logger.info("Reconfiguring slurmctld with previous configuration...")
        result = subprocess.run(['scontrol', 'reconfigure'], 
                               capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logger.info("✓ Successfully restored previous configuration")
            logger.info("Please review the configuration changes and try again")
            logger.info("Check slurmctld logs for details: journalctl -u slurmctld -n 50")
            return True
        else:
            logger.error("Failed to reconfigure slurmctld even with backup configuration")
            logger.error(f"Error: {result.stderr}")
            logger.error("Manual intervention required. Check:")
            logger.error("  - slurmctld logs: journalctl -u slurmctld -n 100")
            logger.error("  - slurm.conf syntax: slurmctld -t")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("scontrol reconfigure timed out during rollback")
        return False
    except Exception as e:
        logger.error(f"Error during rollback: {e}")
        return False