import click
from lib.cli import click_filter_nodes
from lib.ociwrap import run_tag


@click.command()
@click_filter_nodes
@click.pass_context
def tag(ctx, nodes):
    """Tag nodes as unhealthy."""
    for node in nodes:
        run_tag(node)
