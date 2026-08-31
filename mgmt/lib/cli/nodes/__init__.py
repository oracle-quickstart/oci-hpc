import click
from lib.cli.nodes.commands import add_dns_entry, boot_volume_swap, console_history, get, healthchecks, list_cmd, reboot, reconfigure, tag, tag_and_terminate, terminate

@click.group("nodes")
def cmd():
    """Commands to manage nodes."""
    pass

cmd.add_command(list_cmd.list_cmd)
cmd.add_command(boot_volume_swap.boot_volume_swap)
cmd.add_command(terminate.terminate)
cmd.add_command(reboot.reboot)
cmd.add_command(tag.tag)
cmd.add_command(tag_and_terminate.tag_and_terminate)
cmd.add_command(reconfigure.reconfigure)
cmd.add_command(get.get)
cmd.add_command(healthchecks.healthchecks)
cmd.add_command(console_history.console_history)
cmd.add_command(add_dns_entry.add_dns_entry)
cmd.add_command(add_dns_entry.delete_dns_entry)
