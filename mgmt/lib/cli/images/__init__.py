import click
from lib.cli.images.commands import list, create, add_shape

@click.group("images")
def cmd():
    """Commands to manage images."""
    pass

cmd.add_command(list.list_images)
cmd.add_command(create.create)
cmd.add_command(add_shape.add_shape)