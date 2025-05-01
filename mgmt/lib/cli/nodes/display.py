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
            table.add_row("Status", node.status)
            table.add_row("Cluster", node.cluster_name)
            table.add_row("ID", str(node.ocid))
            table.add_row("Serial", node.serial)
            table.add_row("IP", node.ip_address)
            table.add_row("Shape", node.shape)
        else:
            table.add_row("ip_address", node.ip_address)
            table.add_row("controller_status", node.controller_status)
            table.add_row("startedTime", node.startedTime)
            table.add_row("status", node.status)
            table.add_row("AD", node.AD)
            table.add_row("FirstTimeReachable", node.FirstTimeReachable)
            table.add_row("cluster_name", node.cluster_name)
            table.add_row("compartment", node.compartment)
            table.add_row("tenancy", node.tenancy)
            table.add_row("compute_status", node.compute_status)
            table.add_row("controller_name", node.controller_name)
            table.add_row("fss_mount", node.fss_mount)
            table.add_row("hostname", node.hostname)
            table.add_row("hpc_island", node.hpc_island)
            table.add_row("lastTimeReachable", node.lastTimeReachable)
            table.add_row("networkBlockId", node.networkBlockId)
            table.add_row("oci_name", node.oci_name)
            table.add_row("ocid", node.ocid)
            table.add_row("rackID", node.rackID)

            table.add_row("railId", node.railId)
            table.add_row("role", node.role)
            table.add_row("serial", node.serial)
            table.add_row("shape", node.shape)
            table.add_row("terminatedTime", node.terminatedTime)
            table.add_row("update_count", str(node.update_count))
            table.add_row("healthcheck_recomandation", node.healthcheck_recomandation)
            table.add_row("last_healthcheck_time", node.last_healthcheck_time)
            table.add_row("healthcheck_logs", node.healthcheck_logs)      
        console = Console()
        console.print(table)

def print_node_list_json(nodes):
    node_dicts = [node_to_dict(node) for node in nodes]
    print(json.dumps(node_dicts, indent=4))

def print_node_list(nodes, title):
    table = Table(title=title)
    table.add_column("Hostname", justify="left")
    table.add_column("Status", justify="left")
    table.add_column("Compute Status", justify="left")
    table.add_column("HealthCheck", justify="left")
    table.add_column("Cluster", justify="left")
    table.add_column("ID", justify="left")
    table.add_column("Serial", justify="left")
    table.add_column("IP", justify="left")
    table.add_column("Shape", justify="left")

    for node in nodes:
        table.add_row(node.hostname, node.status, node.compute_status, node.healthcheck_recomandation, node.cluster_name, str(node.ocid), node.serial, node.ip_address, node.shape)

    console = Console()
    console.print(table)