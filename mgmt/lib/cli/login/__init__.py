import click
from lib.cli.login.commands import list, create, delete

@click.group("login")
def cmd():
    """Commands to manage login nodes."""
    pass

# Register other commands
cmd.add_command(list.list)
cmd.add_command(create.create)
cmd.add_command(delete.delete)
