import click
from lib.cli.services.commands import run, topology

@click.group("services")
def cmd():
    """Commands to manage services."""
    pass

cmd.add_command(run.all)
cmd.add_command(run.update_metadata)
cmd.add_command(run.scan_queue)
cmd.add_command(run.ansible)
cmd.add_command(run.scan_host_api)
cmd.add_command(run.active_hc)
cmd.add_command(run.multi_node_hc)
cmd.add_command(topology.init)
