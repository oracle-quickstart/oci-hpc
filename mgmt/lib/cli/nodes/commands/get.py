
import click
from lib.cli.nodes.display import print_nodes_info
from lib.database import get_nodes_by_id, get_nodes_by_serial, get_nodes_by_name, get_nodes_by_ip, get_nodes_by_any
from lib.logger import logger

class DefaultCommandGroup(click.Group):
    def parse_args(self, ctx, args):
        # Try to resolve the command name early
        try:
            # Try to get the command to validate it exists
            cmd = self.get_command(ctx, args[0])
        except IndexError:
            cmd = None

        if cmd is None:
            # If the first argument is not a valid command, treat it as an argument to 'any'
            if args:
                if args[0] == "--help":
                    return super().parse_args(ctx, args)
            args.insert(0, 'any')
        return super().parse_args(ctx, args)

@click.group(cls=DefaultCommandGroup)
def get():
    """Get information about nodes. Any is the default"""
    pass

@get.command()
@click.argument('serials', required=True)
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def serials(serials, full):
    """Get information about a node by serial number."""
    nodes = get_nodes_by_serial(serials)

    if not nodes:
        click.echo("node not found.")
        return

    print_nodes_info(nodes, full=full)

@get.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.argument('names', required=True)
def names(names, full):
    """Get information about a node by host name."""
    nodes = get_nodes_by_name(names)

    if not nodes:
        click.echo("Node not found.")
        return

    print_nodes_info(nodes, full=full)

@get.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.argument('ids', required=True)
def ids(ids, full):
    """Get information about a node by ID."""
    nodes = get_nodes_by_id(ids)

    if not nodes:
        click.echo("Node not found.")
        return

    print_nodes_info(nodes, full=full)

@get.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.argument('ips', required=True)
def ips(ips, full):
    """Get information about a node by IP."""
    nodes = get_nodes_by_ip(ips)

    if not nodes:
        click.echo("Node not found.")
        return

    print_nodes_info(nodes, full=full)

@get.command(name='any')
@click.argument('identifiers')
@click.option('--full', is_flag=True, help='Get full information.', default=False)
def any_cmd(identifiers, full):
    """Default: Get info by serial, IP, OCID, or hostname."""
    try:
        nodes = get_nodes_by_any(identifiers)
    except Exception as e:
        logger.error(f"Invalid identifier format: {e}")
        click.echo(f"Error: {e}")
        return

    if not nodes:
        click.echo("Node not found.")
    else:
        print_nodes_info(nodes, full=full)
