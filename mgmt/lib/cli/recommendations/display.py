from rich.table import Table
from rich.console import Console

def print_node_list(nodes, title):
    table = Table(title=title)
    table.add_column("Hostname", justify="left")
    table.add_column("Status", justify="left")
    table.add_column("Controller Status", justify="left")
    table.add_column("Compute Status", justify="left")
    table.add_column("Last Time Reachable", justify="left")
    table.add_column("Node Start Time", justify="left")
    table.add_column("Healthcheck Recommendation", justify="left")
    table.add_column("Cluster", justify="left")
    table.add_column("IP", justify="left")
    table.add_column("Shape", justify="left")

    for node in nodes:
        table.add_row(node.hostname, node.status, node.controller_status, node.compute_status, node.lastTimeReachable, node.startedTime, node.healthcheck_recomandation, node.cluster_name, node.ip_address, node.shape)

    console = Console()
    console.print(table)