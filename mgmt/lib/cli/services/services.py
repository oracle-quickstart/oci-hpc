import click
from lib.cli.services.commands import run

@click.group()
def services():
    """Commands to manage nodes."""
    pass

services.add_command(run.all)
services.add_command(run.update_metadata)
services.add_command(run.scan_queue)
services.add_command(run.ansible)
services.add_command(run.scan_host_api)