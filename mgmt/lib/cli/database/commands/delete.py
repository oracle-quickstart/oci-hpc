import click
from lib.database import get_controller_node, get_nodes_by_any, db_delete_node
from lib.logger import logger
from lib.ociwrap import get_memory_fabrics
from lib.cli.fabrics.display import print_fabrics

@click.command()
@click.argument('identifiers')
def delete(identifiers):
    """List all fabrics for nodes."""

    nodes = get_nodes_by_any(NodeSet(identifiers))
    for node in nodes:
        db_delete_node(node)
