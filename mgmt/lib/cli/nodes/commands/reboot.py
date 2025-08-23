
import click
from lib.ociwrap import run_reboot
from lib.database import get_nodes_by_any, db_update_node
from lib.logger import logger


@click.command()
@click.option("--nodes", required=True, help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)")
@click.option("--soft", required=True, default=False, help="Soft Reboot the node, default is Force Reboot")
def reboot(nodes, soft):
    """Reboot nodes"""

    nodes = get_nodes_by_any(nodes)

    if not nodes:
        click.echo("Node not found.")
        return

    for node in nodes:
        run_reboot(node, soft)
        db_update_node(node, compute_status="starting")
