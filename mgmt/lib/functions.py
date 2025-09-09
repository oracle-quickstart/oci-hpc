from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
from concurrent.futures import ProcessPoolExecutor
from lib.ociwrap import get_host_api_dict
from lib.database import get_all_nodes, db_update_node, get_controller_node, db_get_latest_healthchecks, db_create_healthcheck, db_update_healthcheck

import subprocess
import ipaddress

import sys
import json
version = sys.version_info

if version >= (3, 12):
    from datetime import datetime, timedelta, timezone, UTC
else:
    from datetime import datetime, timedelta, timezone


from lib.logger import logger

curl_timeout=3
unreachable_timeout=timedelta(hours=6)

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

def run_ansible(controller_name):
    command = ". /etc/os-release; /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/bin/ansible-playbook /config/playbooks/manage_nodes.yml"

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
    command = ". /etc/os-release; /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/bin/ansible-playbook /config/playbooks/slurm_init.yml"

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
        time_threshold = (current_time.now(UTC) - unreachable_timeout).replace(tzinfo=timezone.utc)
    else:
        current_time = datetime.utcnow()
        time_threshold = (current_time.utcnow() - unreachable_timeout).replace(tzinfo=timezone.utc)
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
    print(latest_healthchecks)
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
            db_update_healthcheck(passive_hc, {"healthcheck_last_time":kwargs["passive_healthcheck_time"]})

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
                db_update_healthcheck(active_hc, {"healthcheck_last_time":kwargs["active_healthcheck_time"]})

    if "multi_node_healthcheck_status" in kwargs:
        active_hc=None
        status=None
        for healthcheck in latest_healthchecks:
            if healthcheck.healthcheck_type == "multi-node":
                active_hc=healthcheck
                status=healthcheck.healthcheck_status
        if passive_hc is None or (status != kwargs["multi_node_healthcheck_status"]):
            logger.debug(f"Creating multi-node healthcheck for {node_ocid}")
            db_create_healthcheck(node_ocid, {"healthcheck_last_time":kwargs["multi_node_healthcheck_time"],\
                                    "healthcheck_type":"multi-node", \
                                    "healthcheck_logs":kwargs["multi_node_healthcheck_logs"],\
                                    "healthcheck_time_change":kwargs["multi_node_healthcheck_time"],\
                                    "healthcheck_recommendation":kwargs["multi_node_healthcheck_recommendation"],\
                                    "healthcheck_status":kwargs["multi_node_healthcheck_status"],\
                                    "healthcheck_associated_node":json_data["multi_node_healthcheck_associated_node"]})
        else:
            logger.debug(f"Updating multi-node healthcheck for {node_ocid}")
            db_update_healthcheck(healthcheck, {"healthcheck_last_time":kwargs["multi_node_healthcheck_time"]})


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
                db_update_node(node,oci_health=host_api.health,oci_impacted_components=host_api.has_impacted_components,oci_host_id=host_api.id)
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
                ocid_dict[ip_address]=json_data["ocid"]
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
    result = subprocess.run(
        ["sinfo", "-N", "-h", "-o", "%N %R %t"],
        capture_output=True, text=True, check=True
    )
    
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
    return sinfo_dict
