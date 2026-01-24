from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
from concurrent.futures import ProcessPoolExecutor
from lib.ociwrap import get_host_api_dict
from lib.database import get_all_nodes, db_update_node, get_controller_node, db_get_latest_healthchecks, db_create_healthcheck, db_update_healthcheck

import subprocess
import ipaddress
from typing import List
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
    command = "sudo /opt/oci-hpc/healthchecks/gpu_reset.sh --slurm"
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
        
def generate_slurm_entries(configs) -> List[str]:
    """Generate Nodeset and PartitionName entries from database configs."""
    entries = []
    partitions={}
    for config in configs:
        # Add Nodeset entry
        entries.append(f"Nodeset={config.name} Feature={config.name}")
        
        if config.partition in partitions:
            partitions[config.partition]["name"].append(config.name)
        else:
            partitions[config.partition] = {"name":[config.name], "default": "NO"}
        # Add PartitionName entry
        if config.default_partition:
            partitions[config.partition]["default"] = "YES"

            # Special handling for default partition
    for key in partitions:
        PartitionName = key
        Nodes = ",".join(partitions[key]["name"])
        default = partitions[key]["default"]
        entries.append(f"PartitionName={PartitionName} Nodes={Nodes} Default={default}")
    
    return entries

def read_slurm_conf(filepath='/etc/slurm/slurm.conf'):
    """Read slurm.conf and separate managed and unmanaged lines."""
    managed_keywords = ["Nodeset", "PartitionName"]
    ignored_lines = [
        "PartitionName=compute-healthcheck Nodes=default Default=NO PriorityTier=0"
    ]
    
    unmanaged_lines = []
    existing_managed_lines = []
    
    with open(filepath, 'r') as f:
        for line in f:
            stripped = line.rstrip('\n')
            
            # Check if it's an ignored line (keep it as unmanaged)
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

def sync_slurm_config(configs, slurm_conf_path='/etc/slurm/slurm.conf'):
    """Synchronize database configs with slurm.conf."""
    backup_path = f"{slurm_conf_path}.backup"
    
    # Check if modifying a file in /etc and warn if not root
    if slurm_conf_path.startswith('/etc/') and not check_root_privileges():
        return False
    
    try:
        new_managed_entries = generate_slurm_entries(configs)
        unmanaged_lines, existing_managed_lines = read_slurm_conf(slurm_conf_path)
        
        new_set = set(new_managed_entries)
        existing_set = set(existing_managed_lines)
        
        if new_set == existing_set:
            logger.info("No changes detected in slurm.conf - skipping update")
            return True
        
        # Show changes
        added = new_set - existing_set
        removed = existing_set - new_set
        
        if added:
            logger.info("Adding entries:")
            for entry in added:
                logger.info(f"  + {entry}")
        
        if removed:
            logger.info("Removing entries:")
            for entry in removed:
                logger.info(f"  - {entry}")

        # Write updated config (this creates a backup)
        write_slurm_conf(unmanaged_lines, new_managed_entries, slurm_conf_path, backup=True)
        
        # Reconfigure slurmctld to pick up changes
        logger.info("Running 'scontrol reconfigure'...")
        result = subprocess.run(['scontrol', 'reconfigure'], 
                               capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            logger.info("✓ Successfully synchronized slurm.conf and reconfigured slurmctld")
            return True
        else:
            logger.error(f"scontrol reconfigure failed: {result.stderr}")
            rollback_config(slurm_conf_path, backup_path)
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("scontrol reconfigure timed out")
        rollback_config(slurm_conf_path, backup_path)
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