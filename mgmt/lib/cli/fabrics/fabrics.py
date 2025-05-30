import click
from lib.cli.fabrics.commands import list

@click.group()
def fabrics():
    """Commands to display fabrics."""
    pass

fabrics.add_command(list.list)
