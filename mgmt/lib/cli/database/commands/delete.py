import click
from lib.database import get_nodes_by_any, db_delete_node

from ClusterShell.NodeSet import NodeSet

@click.command()
@click.argument('identifiers')
def delete(identifiers):
    """List all fabrics for nodes."""

    nodes = get_nodes_by_any(NodeSet(identifiers))
    for node in nodes:
        db_delete_node(node)
