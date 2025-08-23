import click
from lib.functions import run_configure
from lib.database import get_nodes_by_any, db_update_node


@click.group()
def reconfigure():
    """List commands for nodes."""
    pass


@reconfigure.command()
@click.option('--nodes', required=True, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)')
def controller(nodes):
    """Switch the configure flag in the DB to reconfigure the node on the controller."""
    nodes = get_nodes_by_any(nodes)
    if not nodes:
        click.echo("No nodes found.")
        return

    for node in nodes:
        db_update_node(node, controller_status="reconfiguring")


@reconfigure.command()
@click.option('--nodes', required=True, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)')
def compute(nodes):
    """Rerun the cloud-init script on the nodes."""
    nodes = get_nodes_by_any(nodes)
    if not nodes:
        click.echo("No nodes found.")
        return

    run_configure(nodes)
    for node in nodes:
        db_update_node(node, compute_status="starting")
