
import click
from lib.ociwrap import run_tag
from lib.database import get_nodes_by_any


@click.command()
@click.option('--nodes', required=True, help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)")
def tag(nodes):
    """Tag nodes as unhealthy."""
    nodes = get_nodes_by_any(nodes)

    if not nodes:
        click.echo("Node not found.")
        return

    for node in nodes:
        run_tag(node)
