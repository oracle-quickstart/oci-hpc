import click
from lib.cli.clusters.commands import add, list, create, delete

@click.group()
def clusters():
    """Commands to manage clusters."""
    pass

clusters.add_command(add.add)
clusters.add_command(list.list)
clusters.add_command(create.create)
clusters.add_command(delete.delete)
