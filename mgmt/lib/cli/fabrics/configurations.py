import click
from lib.cli.configurations.commands import list, get, create, delete, update

@click.group()
def configurations():
    """Commands to manage configurations."""
    pass

configurations.add_command(list.list)
configurations.add_command(get.get)
configurations.add_command(create.create)
configurations.add_command(delete.delete)
configurations.add_command(update.update)
