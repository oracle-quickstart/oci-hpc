from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
from concurrent.futures import ProcessPoolExecutor
from lib.ociwrap import get_host_api_dict, list_instance_maintenance_events, get_instance_maintenance_event, reschedule_instance_maintenance_event
from lib.database import get_all_nodes, db_update_node, get_controller_node, db_get_latest_healthchecks, db_create_healthcheck, db_update_healthcheck
import configparser
import os
import re
import subprocess
import ipaddress
import pathlib
from typing import List, Dict, Optional, Tuple, Set
import sys
import time
import json
version = sys.version_info

if version >= (3, 12):
    from datetime import datetime, timedelta, timezone, UTC
else:
    from datetime import datetime, timedelta, timezone


from lib.logger import logger

curl_timeout=1
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


def run_configure(nodes, clush_parallel_executions=10):
    logger.info(f"Restarting the configuration script on: {NodeSet(','.join([node.ip_address for node in nodes]))}")
    task = task_self()
    task.set_info("fanout", clush_parallel_executions)
    task.shell("sudo bash /var/lib/cloud/instance/scripts/part-001", nodes=NodeSet(','.join([node.ip_address for node in nodes])))
    task.run()
    logger.info("Reconfiguration is done, logs are available at /config/logs/")

def run_reset_gpus(node, clush_parallel_executions=10):
    logger.info("Resetting GPUs on: "+str(node.hostname)+" with IP "+str(node.ip_address))
    task = task_self()
    task.set_info("fanout", clush_parallel_executions)
    nodes = NodeSet(str(node.ip_address))
    command = "sudo /opt/oci-hpc/healthchecks/gpu_reset.sh"
    task.run(command, nodes=nodes)
    logger.info("GPU reset script was run. Logs are available at /var/log/healthchecks/latest_gpu_reset.log.")

def run_command(nodes,command,print_output=False,clush_parallel_executions=10):
    logger.debug(f"Running command {command} on: {NodeSet(','.join([node.ip_address for node in nodes]))}")
    task = task_self()
    task.set_info("fanout", clush_parallel_executions) 
    task.shell(command, nodes=NodeSet(','.join([node.ip_address for node in nodes])))
    task.run()
    if print_output:
        for node in nodes:
            logger.info(f"Output from {node.hostname}: ")
            logger.info(f"{task.node_buffer(node.ip_address).decode().strip()}\n")
            logger.info("------------------------------------------------------------------------------------------------")
    else:
        logger.info("Command is done, logs are available at /config/logs/")


MANAGED_HOSTS_START = "# mgmt-managed-hosts - start"
MANAGED_HOSTS_END = "# mgmt-managed-hosts - end"


def _build_hosts_entries(nodes):
    """Return list of "ip\thostname" lines for nodes with both fields present."""
    lines = []
    seen: Set[Tuple[str, str]] = set()
    for node in nodes:
        if not node.ip_address or not node.hostname:
            continue
        key = (node.ip_address, node.hostname)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{node.ip_address}\t{node.hostname}")
    return lines


def update_hosts_on_cluster(nodes: Optional[List]=None, manage_hosts: bool=True, clush_parallel_executions: int=10):
    """Sync /etc/hosts across given nodes (or all DB nodes) if manage_hosts is enabled.

    Only includes nodes that are still active: status == running and not terminating/terminated
    on the controller side. This prevents stale hosts entries for removed nodes.
    """
    if not manage_hosts:
        logger.debug("/etc/hosts management disabled; skipping sync")
        return

    node_list = nodes or get_all_nodes()

    active_nodes = []
    skipped = 0
    for n in node_list:
        if not n.ip_address or not n.hostname:
            skipped += 1
            continue
        if n.status not in ("running", "starting"):
            skipped += 1
            continue
        if n.controller_status in ["terminating", "terminated"]:
            skipped += 1
            continue
        active_nodes.append(n)

    if not active_nodes:
        logger.warning("No active nodes available to update /etc/hosts")
        return

    if skipped:
        logger.info(f"Skipped {skipped} nodes not eligible for /etc/hosts (non-running or missing ip/hostname)")

    hosts_lines = _build_hosts_entries(active_nodes)
    hosts_block = "\n".join([MANAGED_HOSTS_START] + hosts_lines + [MANAGED_HOSTS_END])

    # Bash script preserves loopback entries, replaces only the managed block, overwrites atomically.
    update_script = f"""
set -e
tmp=$(mktemp)
# Remove previous managed block if present
sed '/^{MANAGED_HOSTS_START}$/,/^{MANAGED_HOSTS_END}$/d' /etc/hosts > "$tmp"

# Ensure loopback entries are present
grep -q '^127\\.0\\.0\\.1' "$tmp" || echo '127.0.0.1\tlocalhost\tlocalhost.localdomain\tlocalhost4\tlocalhost4.localdomain4' >> "$tmp"
grep -q '^::1' "$tmp" || echo '::1\tlocalhost\tlocalhost.localdomain\tlocalhost6\tlocalhost6.localdomain6' >> "$tmp"
grep -q '^127\\.0\\.1\\.1' "$tmp" || echo "127.0.1.1\t$(hostname)\t$(hostname)" >> "$tmp"

# Append fresh managed block
cat <<'EOF' >> "$tmp"
{hosts_block}
EOF
sudo cp "$tmp" /etc/hosts
sudo chmod 644 /etc/hosts
rm "$tmp"
"""

    logger.info("Updating /etc/hosts on: %s", NodeSet(','.join([n.ip_address for n in node_list])))
    task = task_self()
    task.set_info("fanout", clush_parallel_executions)
    task.shell(update_script, nodes=NodeSet(','.join([n.ip_address for n in node_list])))
    task.run()
    logger.info("/etc/hosts synchronized on cluster")


def rescan_vcns_from_inventory(manage_hosts: bool=False, cfg: Optional[Dict]=None, prune_missing: bool=False):
    """
    Re-run VCN scans for private/public subnets found in inventory files.
    """
    # Local import to avoid circular dependency at module load
    from lib.cli.database.commands.scan_vcn import scan_vcn_logic

    inventory_candidates = []
    controller = get_controller_node()
    cluster_name = controller.cluster_name if controller else None
    if cluster_name:
        inventory_candidates.append(f"/config/playbooks/inventory_{cluster_name}")
    inventory_candidates.append("/config/playbooks/inventory")

    subnets: Set[str] = set()
    for inv in inventory_candidates:
        path = pathlib.Path(inv)
        if not path.exists():
            continue
        try:
            ansvars = get_ansiblevars(inv, ["private_subnet", "public_subnet"])
            for key in ["private_subnet", "public_subnet"]:
                cidr = ansvars.get(key)
                if cidr:
                    subnets.add(cidr)
        except Exception as exc:
            logger.debug(f"Could not read {inv}: {exc}")

    if not subnets:
        logger.debug("No subnets found to rescan")
        return

    logger.info(f"Rescanning VCNs for /etc/hosts: subnets={sorted(subnets)} manage_hosts={manage_hosts}")

    for cidr in subnets:
        logger.info(f"Auto scanning VCN CIDR {cidr} (manage_hosts={manage_hosts})")
        scan_vcn_logic(cidr, dns=False, change_hostname=False, manage_hosts=manage_hosts, cfg={"manage_hosts": manage_hosts}, prune_missing=prune_missing)


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
            logger.info("Ansible finished succesfully")
            return True
    except Exception as e:
        logger.error(f"Error running ansible: {e}")
        print(result.stdout)
        return False

def run_ansible_slurm_reconcile(controller_name):
    command = ". /etc/os-release; /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci/bin/ansible-playbook /config/playbooks/slurm_reconcile.yml"

    try:
        logger.info("Starting Slurm reconcile: %s", command)
        result = subprocess.run(
            command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, executable="/bin/bash"
        )

        for line in result.stdout.splitlines():
            logger.info("[ansible] %s", line)
        for line in result.stderr.splitlines():
            logger.error("[ansible] %s", line)

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
            if result.stderr:
                print(result.stderr)
            return False
        else:
            logger.info("Ansible finished succesfully")
            return True
    except Exception as e:
        logger.error(f"Error running ansible: {e}")
        if 'result' in locals():
            print(result.stdout)
            if result.stderr:
                print(result.stderr)
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
            db_update_healthcheck(passive_hc, {"healthcheck_last_time":kwargs["passive_healthcheck_time"],"healthcheck_logs":kwargs["passive_healthcheck_logs"],"healthcheck_recommendation":kwargs["passive_healthcheck_recommendation"]})

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
                db_update_healthcheck(active_hc, {"healthcheck_last_time":kwargs["active_healthcheck_time"],"healthcheck_logs":kwargs["active_healthcheck_logs"],"healthcheck_recommendation":kwargs["active_healthcheck_recommendation"]})

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
            db_update_healthcheck(multi_hc, {"healthcheck_last_time":kwargs["multi_node_healthcheck_time"],"healthcheck_logs":kwargs["multi_node_healthcheck_logs"],"healthcheck_recommendation":kwargs["multi_node_healthcheck_recommendation"]})


def scan_host_api_logic(include_hpc_islands=False):
    available_nodes={}
    available_by_hpc_island={}
    controller = get_controller_node()
    if controller is None:
        return ({}, {}) if include_hpc_islands else {}
    host_api_list = get_host_api_dict(controller.compartment_id,controller.tenancy_id)
    if not len(host_api_list):
        return ({}, {}) if include_hpc_islands else {}
    node_list = get_all_nodes()
    for node in node_list:
        for host_api in host_api_list:
            if node.ocid == host_api.instance_id:
                impacted_component_details = getattr(
                    host_api,
                    "impacted_component_details",
                    None,
                )
                db_update_node(
                    node,
                    oci_host_id=host_api.id,
                    oci_impacted_component_details=(
                        json.dumps(impacted_component_details, sort_keys=True)
                        if impacted_component_details is not None
                        else None
                    ),
                )
    for host_api in host_api_list:
        if host_api.instance_id is None and host_api.lifecycle_state == "AVAILABLE":
            if host_api.shape in available_nodes.keys():
                available_nodes[host_api.shape]+=1
            else:
                available_nodes[host_api.shape]=1
            hpc_island_id = getattr(host_api, "hpc_island_id", None)
            if hpc_island_id:
                island_shapes = available_by_hpc_island.setdefault(hpc_island_id, {})
                island_shapes[host_api.shape] = island_shapes.get(host_api.shape, 0) + 1
    if include_hpc_islands:
        return available_nodes, available_by_hpc_island
    return available_nodes

def get_nodes_ocid_by_ip(ip_addresses,HTTP_SERVER_PORT):
    urls=[f"http://{ip_address}:{HTTP_SERVER_PORT}/info" for ip_address in ip_addresses]
    # Keep fanout reasonable to avoid spawning hundreds of worker processes
    max_workers = min(32, max(1, len(urls)))
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        content_results = list(executor.map(fetch_content, urls))
    result_dict = dict(zip(ip_addresses, content_results))
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
        else:
            ocid_dict[ip_address]=None
    return ocid_dict

def get_nodes_ocid_by_subnet(subnet_cidr, HTTP_SERVER_PORT):
    """Scan a subnet and return mapping {ip: ocid} if answering."""
    network = ipaddress.ip_network(subnet_cidr, strict=False)
    ip_addresses = [str(ip) for ip in network.hosts()]
    return get_nodes_ocid_by_ip(ip_addresses,HTTP_SERVER_PORT)

def _slurm_json_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "string", "state", "value", "number"):
            if key in value:
                return _slurm_json_value(value[key])
    return None

def _slurm_json_values(value):
    if value is None:
        return []
    if isinstance(value, list):
        values = []
        for item in value:
            item_value = _slurm_json_value(item)
            if item_value:
                values.append(item_value)
        return values
    if isinstance(value, str):
        return [item for item in value.split(",") if item]
    if isinstance(value, dict):
        for key in ("current", "values", "list"):
            if key in value:
                return _slurm_json_values(value[key])
    item_value = _slurm_json_value(value)
    return [item_value] if item_value else []

def _slurm_nodes_from_json_value(value):
    nodes = []
    for node_expression in _slurm_json_values(value):
        try:
            nodes.extend([str(node) for node in NodeSet(node_expression)])
        except Exception:
            nodes.append(node_expression)
    return nodes

def _slurm_node_start_time(value):
    if value is None:
        return None
    if isinstance(value, dict):
        if value.get("set") is False:
            return None
        for key in ("number", "seconds", "time"):
            parsed = _slurm_node_start_time(value.get(key))
            if parsed is not None:
                return parsed
        return None
    if isinstance(value, (int, float)):
        if value <= 0:
            return None
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        if not value or value.lower() in ("none", "n/a", "null", "unknown"):
            return None
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None

def _slurm_node_uptime(record, current_time):
    start_time = _slurm_node_start_time(
        record.get("slurmd_start_time")
        or record.get("slurmdStartTime")
        or record.get("slurmd_start")
    )
    if start_time is None:
        return 0
    return max(int((current_time - start_time).total_seconds()), 0)

def _slurm_node_reason(record):
    reason = _slurm_json_value(record.get("reason"))
    if not reason or reason.lower() in ("none", "n/a", "null"):
        return None
    return re.sub(r"\s+\[[^]]+\]$", "", reason)

def _add_slurm_node_record(
    sinfo_dict,
    node,
    state,
    partition=None,
    reservation_id=None,
    reason=None,
    slurm_up_time=0,
):
    if node not in sinfo_dict:
        sinfo_dict[node] = {
            "state": state,
            "partition": [],
            "reservation_id": reservation_id,
            "reason": reason,
            "slurm_up_time": slurm_up_time,
        }
    if partition and partition not in sinfo_dict[node]["partition"]:
        sinfo_dict[node]["partition"].append(partition)

def get_slurm_state():
    if version >= (3, 12):
        current_time = datetime.now(UTC)
    else:
        current_time = datetime.now().astimezone(timezone.utc)
        
    try:
        result = subprocess.run(
            ["sinfo", "-N", "--json"],
            capture_output=True, text=True, check=True
        )
        for _ in range(10):
            logger.debug(f"sinfo --json output: {result.stdout}")
            if result.stdout:
                break
            time.sleep(10)
            result = subprocess.run(
                ["sinfo", "-N", "--json"],
                capture_output=True, text=True, check=True
            )
        sinfo_payload = json.loads(result.stdout)

    except Exception as e:
        logger.error(f"Failed to run sinfo --json: {e}")
        return {}
    sinfo_dict = {}

    for record in sinfo_payload.get("sinfo", []):
        if not isinstance(record, dict):
            continue
        partition_info = record.get("partition")
        if isinstance(partition_info, dict):
            partition = _slurm_json_value(partition_info.get("name"))
        else:
            partition = _slurm_json_value(partition_info)

        node_info = record.get("node")
        state_values = (
            _slurm_json_values(node_info.get("state"))
            if isinstance(node_info, dict)
            else []
        )
        state = "+".join(state_values).lower() or "unknown"

        nodes_info = record.get("nodes")
        if not isinstance(nodes_info, dict):
            continue
        reservation = _slurm_json_value(record.get("reservation"))
        if not reservation or reservation.lower() in ("none", "n/a", "null"):
            reservation = None
        for node in _slurm_nodes_from_json_value(nodes_info.get("nodes")):
            _add_slurm_node_record(
                sinfo_dict,
                node,
                state,
                partition=partition,
                reservation_id=reservation,
                reason=_slurm_node_reason(record),
                slurm_up_time=_slurm_node_uptime(record, current_time),
            )

    nodes_needing_details = [
        node
        for node, details in sinfo_dict.items()
        if details["reason"] is None or not details["slurm_up_time"]
    ]
    if not nodes_needing_details:
        return sinfo_dict

    try:
        result = subprocess.run(
            ["scontrol", "show", "node", "--json"],
            capture_output=True, text=True, check=True
        )
        scontrol_payload = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        output = (
            (exc.stderr or exc.stdout or str(exc)).strip()
            if isinstance(exc, subprocess.CalledProcessError)
            else str(exc)
        )
        logger.warning("Skipping Slurm node details because scontrol show node --json failed: %s", output)
        return sinfo_dict

    scontrol_nodes = {
        _slurm_json_value(record.get("name")): record
        for record in scontrol_payload.get("nodes", [])
        if isinstance(record, dict) and _slurm_json_value(record.get("name"))
    }
    for node in nodes_needing_details:
        record = scontrol_nodes.get(node)
        if record is None:
            logger.warning("Skipping Slurm details for %s because it was not returned by scontrol", node)
            continue
        if sinfo_dict[node]["reason"] is None:
            sinfo_dict[node]["reason"] = _slurm_node_reason(record)
        if not sinfo_dict[node]["slurm_up_time"]:
            sinfo_dict[node]["slurm_up_time"] = _slurm_node_uptime(record, current_time)


    return sinfo_dict


def update_slurm_node_state(node, state, reason=None):
    """Set a Slurm node state and return whether scontrol succeeded."""
    command = [
        "sudo",
        "scontrol",
        "update",
        f"NodeName={node.hostname}",
        f"State={state}",
    ]
    if reason:
        command.append(f"Reason={reason}")

    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info("Set Slurm node %s to %s", node.hostname, state)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Failed to set Slurm node %s to %s: %s",
            node.hostname,
            state,
            exc.stderr or exc.stdout or exc,
        )
        return False


IGNORED_MAINTENANCE_EVENT_STATES = {"FAILED", "CANCELED"}
MAINTENANCE_EVENT_STATE_PRIORITY = {
    "SCHEDULED": 0,
    "STARTED": 1,
    "PROCESSING": 2,
    "SUCCEEDED": 3,
}
SLURM_MAINTENANCE_EVENT_NAMES = {
    "DOWNTIME_HOST_MAINTENANCE",
    "LIVE_HOST_MAINTENANCE",
}
SLURM_MAINTENANCE_REASON_PREFIX = "OCI-IME::"
MAINTENANCE_EVENT_SCHEDULED_WINDOW_LIMIT = timedelta(minutes=5)


def _maintenance_event_sort_key(event):
    state = str(getattr(event, "lifecycle_state", "")).upper()
    time_window_start = getattr(event, "time_window_start", None)
    return (
        MAINTENANCE_EVENT_STATE_PRIORITY.get(state, 99),
        str(time_window_start or "9999-12-31T23:59:59Z"),
        str(getattr(event, "id", "")),
    )


def _select_instance_maintenance_event(events):
    candidates = [
        event
        for event in events
        if str(getattr(event, "lifecycle_state", "")).upper()
        not in IGNORED_MAINTENANCE_EVENT_STATES
    ]
    if not candidates:
        return None
    return min(candidates, key=_maintenance_event_sort_key)


def _serialize_oci_datetime(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _maintenance_event_fault_ids(event):
    additional_details = getattr(event, "additional_details", None)
    if not isinstance(additional_details, dict):
        return []

    fault_details = additional_details.get("faultDetails")
    if not fault_details:
        return []

    if isinstance(fault_details, str):
        try:
            fault_details = json.loads(fault_details)
        except ValueError:
            return []

    if isinstance(fault_details, dict):
        fault_details = [fault_details]
    if not isinstance(fault_details, list):
        return []

    fault_ids = set()
    for fault_detail in fault_details:
        if not isinstance(fault_detail, dict):
            continue
        fault_id = fault_detail.get("faultId")
        if fault_id:
            fault_ids.add(str(fault_id))
    return sorted(fault_ids)


def _maintenance_event_error_code(event):
    fault_ids = _maintenance_event_fault_ids(event)
    if not fault_ids:
        return None
    return ",".join(fault_ids)


def _maintenance_event_with_details(event):
    if _maintenance_event_fault_ids(event):
        return event

    event_id = getattr(event, "id", None)
    if not event_id:
        return event

    return get_instance_maintenance_event(event_id) or event


def _maintenance_event_db_values(event):
    return {
        "maintenance_event_display_name": getattr(event, "display_name", None),
        "maintenance_event_error_code": _maintenance_event_error_code(event),
        "maintenance_event_id": getattr(event, "id", None),
        "maintenance_event_lifecycle_state": getattr(event, "lifecycle_state", None),
        "maintenance_event_time_started": _serialize_oci_datetime(
            getattr(event, "time_started", None)
        ),
        "maintenance_event_time_finished": _serialize_oci_datetime(
            getattr(event, "time_finished", None)
        ),
        "maintenance_event_time_window_start": _serialize_oci_datetime(
            getattr(event, "time_window_start", None)
        ),
    }


def _maintenance_event_utc_datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _maintenance_event_is_scheduled_far_future(event):
    time_window_start = getattr(event, "time_window_start", None)
    if not time_window_start:
        return False
    time_window_start = _maintenance_event_utc_datetime(time_window_start)
    scheduled_window_limit = (
        datetime.now(timezone.utc) + MAINTENANCE_EVENT_SCHEDULED_WINDOW_LIMIT
    )
    return time_window_start > scheduled_window_limit


def _slurm_state_is_drained(slurm_state):
    state_components = {
        component.strip()
        for component in re.split(r"[+,]", str(slurm_state or "").lower())
    }
    return "drain" in state_components


def _maintenance_events_by_instance(node_list, nodes_by_ocid):
    events_by_instance = {}

    compartment_ids = {
        node.compartment_id
        for node in node_list
        if getattr(node, "compartment_id", None)
    }
    for compartment_id in sorted(compartment_ids):
        events = list_instance_maintenance_events(compartment_id)
        for event in events:
            instance_id = getattr(event, "instance_id", None)
            if instance_id not in nodes_by_ocid:
                logger.debug(
                    "Ignoring maintenance event %s for instance %s not present in the DB",
                    getattr(event, "id", None),
                    instance_id,
                )
                continue
            events_by_instance.setdefault(instance_id, []).append(event)

    return events_by_instance


def _maintenance_event_is_current_state(node, event, lifecycle_state):
    if lifecycle_state == "SCHEDULED" and _maintenance_event_is_scheduled_far_future(event):
        return False
    return (
        getattr(node, "maintenance_event_id", None) == getattr(event, "id", None)
        and str(getattr(node, "maintenance_event_lifecycle_state", "")).upper()
        == lifecycle_state
    )


def _reschedule_maintenance_event(node, event):
    event_id = getattr(event, "id", None)
    updated_event, updated_time_window_start = reschedule_instance_maintenance_event(event_id)
    if updated_time_window_start is None:
        return None

    if updated_event is not None:
        event = updated_event
    else:
        event.time_window_start = updated_time_window_start
    logger.info(
        "Moved OCI maintenance event %s start window to %s for %s",
        event_id,
        updated_time_window_start.isoformat(),
        node.hostname,
    )
    return event


def _handle_scheduled_maintenance_event(node, event, slurm_info):
    event_id = getattr(event, "id", None)
    display_name = getattr(event, "display_name", None)

    if slurm_info:
        if _slurm_state_is_drained(slurm_info.get("state")):
            slurm_reason = str(slurm_info.get("reason") or "").lower()
            if slurm_reason.startswith("healthcheck::"):
                if update_slurm_node_state(
                    node,
                    "DRAIN",
                    reason=f"{SLURM_MAINTENANCE_REASON_PREFIX} {display_name}",
                ):
                    return event
                return None
            return event
        if _maintenance_event_is_scheduled_far_future(event):
            event = _reschedule_maintenance_event(node, event)
            if event is None:
                return None
        if update_slurm_node_state(
            node,
            "DRAIN",
            reason=f"{SLURM_MAINTENANCE_REASON_PREFIX} {display_name}",
        ):
            return event
        return None

    if node.role == "compute":
        logger.warning(
            "Deferring OCI maintenance event %s because %s is absent from Slurm",
            event_id,
            node.hostname,
        )
        return None

    return event


def _handle_active_maintenance_event(node, event, slurm_info):
    event_id = getattr(event, "id", None)
    display_name = getattr(event, "display_name", None)

    if slurm_info:
        slurm_state = slurm_info.get("state")
        slurm_reason = str(slurm_info.get("reason") or "").lower()
        if (
            not _slurm_state_is_drained(slurm_state)
            or slurm_reason.startswith("healthcheck::")
        ):
            if update_slurm_node_state(
                node,
                "DRAIN",
                reason=f"{SLURM_MAINTENANCE_REASON_PREFIX} {display_name}",
            ):
                return event
            return None
        return event

    if node.role == "compute":
        logger.warning(
            "Deferring OCI maintenance event %s because %s is absent from Slurm",
            event_id,
            node.hostname,
        )
        return None

    return event


def _handle_succeeded_maintenance_event(node, event, slurm_info):
    event_id = getattr(event, "id", None)

    if slurm_info:
        slurm_state = slurm_info.get("state")
        slurm_reason = str(slurm_info.get("reason") or "")
        if _slurm_state_is_drained(slurm_state):
            if slurm_reason.startswith(SLURM_MAINTENANCE_REASON_PREFIX):
                if update_slurm_node_state(node, "RESUME"):
                    return event
                return None
            logger.warning(
                "Leaving %s drained because its reason is not owned by OCI-IME: %s",
                node.hostname,
                slurm_reason or "<none>",
            )
        return event

    if node.role == "compute":
        logger.warning(
            "Deferring completion of OCI maintenance event %s because %s is absent from Slurm",
            event_id,
            node.hostname,
        )
        return None

    return event


def _handle_maintenance_event(
    node,
    event,
    slurm_info,
    manage_slurm=True,
    healthcheck_drained_only=False,
):
    display_name = getattr(event, "display_name", None)
    lifecycle_state = str(getattr(event, "lifecycle_state", "")).upper()
    slurm_state = slurm_info.get("state") if slurm_info else None
    slurm_reason = str(slurm_info.get("reason") or "").lower() if slurm_info else ""
    healthcheck_drained = (
        slurm_info
        and _slurm_state_is_drained(slurm_state)
        and slurm_reason.startswith("healthcheck::")
    )
    manage_event_slurm = manage_slurm and (
        not healthcheck_drained_only or healthcheck_drained
    )
    maintenance_should_own_slurm = (
        manage_event_slurm
        and lifecycle_state in {"SCHEDULED", "STARTED", "PROCESSING"}
        and slurm_info
        and (
            not _slurm_state_is_drained(slurm_state)
            or slurm_reason.startswith("healthcheck::")
        )
    )

    if display_name not in SLURM_MAINTENANCE_EVENT_NAMES:
        return event
    if _maintenance_event_is_current_state(
        node,
        event,
        lifecycle_state,
    ) and not maintenance_should_own_slurm:
        return event

    if lifecycle_state in {"SCHEDULED", "STARTED", "PROCESSING"} and not manage_event_slurm:
        return event

    if lifecycle_state == "SCHEDULED":
        return _handle_scheduled_maintenance_event(node, event, slurm_info)
    if lifecycle_state in {"STARTED", "PROCESSING"}:
        return _handle_active_maintenance_event(node, event, slurm_info)
    if lifecycle_state == "SUCCEEDED":
        return _handle_succeeded_maintenance_event(node, event, slurm_info)
    return event


def _store_maintenance_event(node, event):
    event = _maintenance_event_with_details(event)
    db_update_node(node, **_maintenance_event_db_values(event))


def process_instance_maintenance_events(
    node_list,
    slurm_dict,
    manage_slurm=True,
    healthcheck_drained_only=False,
):
    nodes_by_ocid = {node.ocid: node for node in node_list if node.ocid}
    events_by_instance = _maintenance_events_by_instance(node_list, nodes_by_ocid)

    for instance_id, events in events_by_instance.items():
        node = nodes_by_ocid[instance_id]
        event = _select_instance_maintenance_event(events)
        if event is None:
            logger.debug(
                "Ignoring FAILED/CANCELED maintenance events for %s",
                node.hostname or node.ocid,
            )
            continue

        event_to_store = _handle_maintenance_event(
            node,
            event,
            slurm_dict.get(node.hostname),
            manage_slurm=manage_slurm,
            healthcheck_drained_only=healthcheck_drained_only,
        )
        if event_to_store is not None:
            _store_maintenance_event(node, event_to_store)


def _node_display_name(node):
    return getattr(node, "hostname", None) or getattr(node, "ocid", None) or "<unknown>"

def _healthcheck_partitions(node):
    slurm_partition = getattr(node, "slurm_partition", None)
    if slurm_partition in (None, "", "None"):
        logger.error(
            "Cannot submit healthcheck for %s: slurm_partition is not set",
            _node_display_name(node),
        )
        return None
    return [
        partition
        for partition in str(slurm_partition).split(',')
        if 'healthcheck' in partition
    ]

def _multi_node_healthcheck_gpu_count(nodes):
    gpu_counts = []
    for node in nodes:
        shape = getattr(node, "shape", None)
        try:
            gpu_count = int(str(shape).split(".")[-1])
        except (TypeError, ValueError):
            logger.warning(
                "Cannot determine GPU count for %s from shape %s",
                _node_display_name(node),
                shape,
            )
            continue
        if gpu_count > 0:
            gpu_counts.append(gpu_count)

    if not gpu_counts:
        logger.warning("Cannot determine GPU count for multi-node healthcheck; defaulting to 8")
        return "8"

    if len(set(gpu_counts)) > 1:
        logger.warning(
            "Multi-node healthcheck nodes have different GPU counts %s; using %s",
            sorted(set(gpu_counts)),
            min(gpu_counts),
        )

    return str(min(gpu_counts))

def run_active_hc(node,reservation_id=None):
    hc_partition = _healthcheck_partitions(node)
    if hc_partition is None:
        return
    if hc_partition:
        logger.debug(f"Submitting active healthcheck on {node.hostname} through partition {hc_partition[0]}")
        if reservation_id is None:
            cmd=["sbatch","-N","1","-p",hc_partition[0],"-w",node.hostname,"--deadline=now+8minutes","--time=00:07:00","/opt/oci-hpc/healthchecks/active_HC.sbatch"]        
        else:
            cmd=["sbatch","-N","1","-p",hc_partition[0],"-w",node.hostname,"--reservation",reservation_id,"--deadline=now+8minutes","--time=00:07:00","/opt/oci-hpc/healthchecks/active_HC.sbatch"]
        logger.debug(f"Running command: {' '.join(cmd)}")
        results = subprocess.run(cmd)
        if results.returncode != 0:
            logger.error(
                "Failed to submit active healthcheck for %s with sbatch "
                "(return code %s): %s",
                node.hostname,
                results.returncode,
                " ".join(cmd),
            )
    else:
        logger.warning(f"No healthcheck partition found for {node.hostname}")

def run_multi_node_active_hc(nodes,exclude_node=None,reservation_id=None):
    hostnames = ",".join([_node_display_name(node) for node in nodes])
    if len(nodes)==1:
        node=nodes[0]
        hc_partition = _healthcheck_partitions(node)
        if hc_partition is None:
            return
    elif len(nodes)==2:
        node_1=nodes[0]
        node_2=nodes[1]
        hc_partition_1 = _healthcheck_partitions(node_1)
        hc_partition_2 = _healthcheck_partitions(node_2)
        if hc_partition_1 is None or hc_partition_2 is None:
            return
        hc_partition=list(set(hc_partition_1) & set(hc_partition_2))
    else:
        logger.error("The number of nodes does not make sense")
        return
    if hc_partition:
        logger.info(f"Submitting multi node healthcheck on {hostnames} through partition {hc_partition[0]}")
        healthcheck_script="/opt/oci-hpc/healthchecks/multi_node_active_HC.sbatch"
        gpu_count = _multi_node_healthcheck_gpu_count(nodes)
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
            logger.error(
                "Failed to submit multi-node active healthcheck for %s with sbatch "
                "(return code %s): %s",
                hostnames,
                results.returncode,
                " ".join(cmd),
            )
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


def delete_nodes_from_slurm(nodes):
    """Delete given nodes from SLURM
    """
    if len(nodes) == 0:
        logger.debug("No nodes found to delete")
        return

    for node in nodes:
        try:
            subprocess.run(
                [
                    "sudo",
                    "scontrol",
                    "delete",
                    f"NodeName={node.hostname}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            nodenames = ",".join([node.hostname for node in nodes])
            logger.error(f"Failed to delete {nodenames} from SLURM: {e}: {e.output}")


def remove_nodes_from_reservation(nodes, name="InitialValidation"):
    """Remove given nodes from the SLURM reservation

    Will remove the reservation as required, as SLURM does not allow for reservations
    without any nodes.
    """
    if len(nodes) == 0:
        logger.debug("No nodes found to remove reservation")
        return

    def _slurm_hostlist(nodes) -> str:
        nodenames = ",".join([node.hostname for node in nodes])
        try:
            return subprocess.check_output(
                ["scontrol", "show", "hostlist", nodenames],
                stderr=subprocess.STDOUT,
            ).decode("utf-8").strip()
        except subprocess.CalledProcessError as e:
            output = e.output.decode("utf-8", errors="replace").strip()
            logger.warning(f"Failed to format SLURM hostlist for {nodenames}: {e}: {output}")
            return nodenames

    def _remove(nodes) -> bool:
        nodenames = ",".join([node.hostname for node in nodes])
        slurm_hostlist = _slurm_hostlist(nodes)
        try:
            subprocess.check_call(
                [
                    "sudo",
                    "scontrol",
                    "update",
                    "reservation",
                    f"reservation={name}",
                    f"Nodes-={slurm_hostlist}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            return True
        except subprocess.CalledProcessError as e:
            output = (e.output or b"").decode("utf-8", errors="replace").strip()
            logger.error(f"Failed to remove {nodenames} ({slurm_hostlist}) from reservation {name}: {e}: {output}")
            return False

    if _remove(nodes):
        logger.debug(f"Successfully removed nodes from reservation {name} in bulk")
    elif all(_remove([node]) for node in nodes):
        logger.debug(f"Successfully removed nodes from reservation {name} individually")
    else:
        try:
            output = subprocess.check_output(
                ["sudo", "scontrol", "show", "reservation", name],
                stderr=subprocess.STDOUT,
            ).decode("utf-8")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list information for reservation {name}: {e}")

        nodelist, = [s for s in output.split() if s.startswith("Nodes=")]
        reserved_nodes = nodelist[6:].split(",")
        if len(reserved_nodes) == 1:
            try:
                subprocess.check_call(
                    ["sudo", "scontrol", "delete", "reservation", name],
                    stderr=subprocess.STDOUT,
                )
                logger.debug(f"Successfully deleted reservation {name}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to delete reservation {name}: {e}")
        else:
            logger.error(f"Failed to remove nodes from reservation {name}")

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
        "VM.DenseIO.E4.Flex", "VM.DenseIO.E5.Flex", "VM.DenseIO.E6.Ax.Flex"
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
    Get list of active nodes in a partition using sinfo JSON output.
    
    Args:
        partition_name: Name of the partition
    
    Returns:
        Set of active node names
    """
    try:
        result = subprocess.run(
            ['sinfo', '-p', partition_name, '-N', '--json'],
            capture_output=True, text=True, timeout=10, check=True
        )
        sinfo_payload = json.loads(result.stdout)
        
        active_nodes = set()
        for record in sinfo_payload.get("sinfo", []):
            if not isinstance(record, dict):
                continue
            partition_info = record.get("partition")
            if isinstance(partition_info, dict):
                record_partition = _slurm_json_value(partition_info.get("name"))
            else:
                record_partition = _slurm_json_value(partition_info)
            if record_partition and record_partition != partition_name:
                continue

            node_info = record.get("node")
            state_values = (
                _slurm_json_values(node_info.get("state"))
                if isinstance(node_info, dict)
                else []
            )
            state = "+".join(state_values).lower()
            nodes_info = record.get("nodes")
            if "idle~" not in state and "down" not in state:
                if isinstance(nodes_info, dict):
                    active_nodes.update(
                        _slurm_nodes_from_json_value(nodes_info.get("nodes"))
                    )
        
        return active_nodes
        
    except subprocess.CalledProcessError as e:
        output = (e.stderr or e.stdout or str(e)).strip()
        logger.warning(f"Failed to query nodes for partition {partition_name}: {output}")
        return set()
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
                            logger.error("This indicates nodes are currently running. Aborting changes.")
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
