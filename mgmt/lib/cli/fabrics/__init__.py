import click
from lib.cli.fabrics.commands import list

@click.group("fabrics")
def cmd():
    """Commands to display fabrics."""
    pass

cmd.add_command(list.list)
