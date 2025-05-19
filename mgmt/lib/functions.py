from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
from concurrent.futures import ProcessPoolExecutor
from lib.oci import get_host_api_dict
from lib.database import get_all_nodes, db_update_node, get_controller_node

import subprocess

import sys
import json
version = sys.version_info

if version >= (3, 12):
    from datetime import datetime, timedelta, timezone , UTC
else:
    from datetime import datetime, timedelta, timezone


from lib.logger import logger
import sys
import random, string

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
    try:
        command = ". /config/venv/bin/activate; ansible-playbook /config/playbooks/manage_nodes.yml"
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        last_line=[s for s in result.stdout.split('\n') if s.startswith(controller_name)][-1]
        failure_count=int([s for s in last_line.split(' ') if s.startswith('failed')][-1].split('=')[1])+int([s for s in last_line.split(' ') if s.startswith('unreachable')][-1].split('=')[1])
        if failure_count:
            print(result.stdout)
            return False
        else:
            logger.info(f"Ansible finished succesfully")
            return True
    except Exception as e:
        logger.info(f"Error running ansible: {e}")
        print(result.stdout)
        return False

def update_nodes_based_on_url(nodes,HTTP_SERVER_PORT):
    update_dict={}

    if version >= (3, 12):
        current_time = datetime.now(UTC)
        time_threshold = (current_time.now(UTC) - unreachable_timeout).replace(tzinfo=timezone.utc)
    else:
        current_time = datetime.utcnow()
        time_threshold = (current_time.utcnow() - unreachable_timeout).replace(tzinfo=timezone.utc)
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")

    ip_addresses = [node.ip_address for node in nodes]        
    urls=[f"http://{ip_address}:{HTTP_SERVER_PORT}/info" for ip_address in ip_addresses]
    with ProcessPoolExecutor(max_workers=10) as executor:
        content_results = list(executor.map(fetch_content, urls))
    result_dict = dict(zip(ip_addresses, content_results))
    for node in nodes:
        update_dict[node.ocid]={}
        content=result_dict[node.ip_address]
        url=f"http://{node.ip_address}:{HTTP_SERVER_PORT}/info"
        if content:
            try:
                json_data = json.loads(content)
                json_data["lastTimeReachable"]=current_time_str
                json_data["ip_address"]=node.ip_address
                if node.status=="starting":
                    json_data["controller_status"]="configuring"
                    json_data["status"]="running"
                if node.FirstTimeReachable is None:
                    json_data.update({"FirstTimeReachable":current_time_str})
                logger.info(f"Stored content for {url}")
                update_dict[node.ocid]=json_data

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode JSON from {url}: {e}")

        else:
            if node.status != "starting":
                if node.lastTimeReachable is None:
                    logger.info(f"Node {node.hostname} was not reachable")
                else:
                    last_time_reachable = datetime.strptime(node.lastTimeReachable, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    if last_time_reachable < time_threshold:
                        update_dict[node.ocid]={"status":"unreachable"}
                        logger.warning(f"Node {node.hostname} was not reachable for 6 hours")
                    else:
                        logger.error(f"Node {node.hostname} was not reachable")
            else:
                logger.warning(f"Node with {node.ip_address} is not ready yet. The webserver containing the node info is not available")
    return update_dict

def scan_host_api_logic():
    available_nodes={}
    controller = get_controller_node()
    if controller is None:
        return {}
    host_api_list = get_host_api_dict(controller.compartment,controller.tenancy)
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