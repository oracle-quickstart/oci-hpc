import click
from lib.cli.configurations.commands import list, get, create, delete, update, update_slurm

@click.group("configurations")
def cmd():
    """Commands to manage configurations."""
    pass

cmd.add_command(list.list)
cmd.add_command(get.get)
cmd.add_command(create.create)
cmd.add_command(delete.delete)
cmd.add_command(update.update)
cmd.add_command(update_slurm.update_slurm)
