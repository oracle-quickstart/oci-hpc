import click
import lib.database as db

from lib.cli import click_filter_nodes


@click.command()
@click_filter_nodes
def delete(nodes):
    """Delete nodes from the DB. This will not terminate the nodes"""
    for node in nodes:
        db.db_delete_node(node)
