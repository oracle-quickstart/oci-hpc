import click
from lib.cli.recommendations.commands import recom

@click.group()
def recommendations():
    """Commands to show recommendations about the cluster."""
    pass

recommendations.add_command(recom.list)
recommendations.add_command(recom.run)
