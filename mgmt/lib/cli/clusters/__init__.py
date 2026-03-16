import click
from lib.cli.clusters.commands import add, list, create, delete
from lib.cli.clusters.commands.update_instance_config import update_instance_config

@click.group("clusters")
def cmd():
    """Commands to manage clusters."""
    pass

# Register the 'add' command group
cmd.add_command(add.add)

# Register other commands
cmd.add_command(list.list)
cmd.add_command(create.create)
cmd.add_command(delete.delete)
cmd.add_command(update_instance_config)
