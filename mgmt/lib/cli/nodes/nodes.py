import click
from lib.cli.nodes.commands import boot_volume_swap, list, get, tag_and_terminate, terminate, reboot, tag, reconfigure

@click.group()
def nodes():
    """Commands to manage nodes."""
    pass

nodes.add_command(list.list)
nodes.add_command(get.get)
nodes.add_command(boot_volume_swap.boot_volume_swap)
nodes.add_command(terminate.terminate)
nodes.add_command(reboot.reboot)
nodes.add_command(tag.tag)
nodes.add_command(tag_and_terminate.tag_and_terminate)
nodes.add_command(reconfigure.reconfigure)
