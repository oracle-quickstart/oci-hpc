import click
from lib.cli.database.commands import add, delete, scan_vcn

@click.group("database")
def cmd():
    """Commands to do in the database."""
    pass

cmd.add_command(add.add)
cmd.add_command(delete.delete)
cmd.add_command(scan_vcn.scan_vcn)
