import rich
import rich.table

def print_node_list(nodes, title):
    table = rich.table.Table(title=title)
    table.add_column("hostname", justify="left")
    table.add_column("status", justify="left")
    table.add_column("compute_status", justify="left")
    table.add_column("passive_healthcheck_recommendation", justify="left")
    table.add_column("cluster_name", justify="left")
    table.add_column("memory_cluster_id", justify="left")
    table.add_column("ocid", justify="left")
    table.add_column("serial", justify="left")
    table.add_column("ip_address", justify="left")
    table.add_column("shape", justify="left")

    for node in nodes:
        table.add_row(
            node.hostname, node.status, node.compute_status,
            node.passive_healthcheck_recommendation, node.cluster_name,
            node.memory_cluster_id, str(node.ocid), node.serial,
            node.ip_address, node.shape
        )

    console = rich.get_console()
    console.print(table)


def print_ime_node_list(nodes, title):
    """Display the selected OCI event beside the passive HC recommendation."""
    table = rich.table.Table(title=title)
    for column in (
        "hostname",
        "ime_recommendation",
        "maintenance_event_lifecycle_state",
        "maintenance_event_error_code",
        "passive_healthcheck_recommendation",
        "maintenance_event_time_window_start",
    ):
        table.add_column(column, justify="left")

    for node in nodes:
        table.add_row(
            node.hostname,
            node.ime_recommendation,
            node.maintenance_event_lifecycle_state,
            node.maintenance_event_error_code or "",
            node.passive_healthcheck_recommendation or "",
            node.maintenance_event_time_window_start or "",
        )

    rich.get_console().print(table)
