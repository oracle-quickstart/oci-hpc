import click
from lib.cli.clusters.commands import add, list, create, delete

@click.group("clusters")
def cmd():
    """Commands to manage clusters."""
    pass

cmd.add_command(add.add)
cmd.add_command(add.add_memory_fabric)
cmd.add_command(list.list)
cmd.add_command(create.create)
cmd.add_command(delete.delete)
