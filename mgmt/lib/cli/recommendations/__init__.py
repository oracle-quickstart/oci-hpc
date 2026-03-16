import click
from lib.cli.recommendations.commands import recom

@click.group("recommendations")
def cmd():
    """Commands to show recommendations about the cluster."""
    pass

cmd.add_command(recom.list)
cmd.add_command(recom.run)
