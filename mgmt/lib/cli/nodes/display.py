from rich.table import Table
from rich.console import Console
import json
from lib.database import node_to_dict

def print_nodes_info(nodes, full=False):
    
    for node in nodes:    
        table = Table(show_header=False, show_lines=True)
        table.add_column(justify="left")
        table.add_column(justify="left")
        if not full:
            table.add_row("Hostname", node.hostname)
            table.add_row("status", node.status)
            table.add_row("Cluster", node.cluster_name)
            table.add_row("ID", str(node.ocid))
            table.add_row("Serial", node.serial)
            table.add_row("IP", node.ip_address)
            table.add_row("Shape", node.shape)
        else:
            table.add_row("ip_address", node.ip_address)
            table.add_row("controller_status", node.controller_status)
            table.add_row("started_time", node.started_time)
            table.add_row("status", node.status)
            table.add_row("availability_domain", node.availability_domain)
            table.add_row("first_time_reachable", node.first_time_reachable)
            table.add_row("cluster_name", node.cluster_name)
            table.add_row("compartment_id", node.compartment_id)
            table.add_row("tenancy_id", node.tenancy_id)
            table.add_row("compute_status", node.compute_status)
            table.add_row("controller_name", node.controller_name)
            table.add_row("fss_mount", node.fss_mount)
            table.add_row("gpu_memory_fabric", node.gpu_memory_fabric)
            table.add_row("hostname", node.hostname)
            table.add_row("hpc_island", node.hpc_island)
            table.add_row("image_id", node.image_id)
            table.add_row("last_time_reachable", node.last_time_reachable)
            table.add_row("network_block_id", node.network_block_id)
            table.add_row("memory_cluster_name", node.memory_cluster_name)
            table.add_row("oci_name", node.oci_name)
            table.add_row("ocid", node.ocid)
            table.add_row("rack_id", node.rack_id)
            table.add_row("rail_id", node.rail_id)
            table.add_row("role", node.role)
            table.add_row("serial", node.serial)
            table.add_row("shape", node.shape)
            table.add_row("terminated_time", node.terminated_time)
            table.add_row("update_count", str(node.update_count))
            table.add_row("healthcheck_recommendation", node.healthcheck_recommendation)
            table.add_row("last_healthcheck_time", node.last_healthcheck_time)
            table.add_row("healthcheck_logs", node.healthcheck_logs)      
        console = Console()
        console.print(table)

def print_node_list_json(nodes):
    node_dicts = [node_to_dict(node) for node in nodes]
    print(json.dumps(node_dicts, indent=4))

def print_node_list(nodes, title):
    table = Table(title=title)
    table.add_column("hostname", justify="left")
    table.add_column("status", justify="left")
    table.add_column("compute_status", justify="left")
    table.add_column("healthcheck_recommendation", justify="left")
    table.add_column("cluster_name", justify="left")
    table.add_column("memory_cluster_name", justify="left")
    table.add_column("ocid", justify="left")
    table.add_column("serial", justify="left")
    table.add_column("ip_address", justify="left")
    table.add_column("shape", justify="left")

    for node in nodes:
        table.add_row(node.hostname, node.status, node.compute_status, node.healthcheck_recommendation, node.cluster_name,node.memory_cluster_name, str(node.ocid), node.serial, node.ip_address, node.shape)

    console = Console()
    console.print(table)