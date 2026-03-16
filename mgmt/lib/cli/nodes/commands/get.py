
import click
from lib.cli.nodes.display import display_nodes, parse_fields_spec
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
@click.option(
    "--format",
    type=click.Choice(["node", "csv", "json"]),
    default="node", show_default=True,
    help="Output format"
)
def serials(serials, format):
    """Get information about a node by serial number."""
    nodes = get_nodes_by_serial(serials)

    if not nodes:
        click.echo("Node not found.")
    else:
        display_nodes(nodes, format, parse_fields_spec("all"), table_style=None, one_line=False, show_header=True, width=None)

@get.command()
@click.argument('names', required=True)
@click.option(
    "--format",
    type=click.Choice(["node", "csv", "json"]),
    default="node", show_default=True,
    help="Output format"
)
def names(names, format):
    """Get information about a node by host name."""
    nodes = get_nodes_by_name(names)

    if not nodes:
        click.echo("Node not found.")
    else:
        display_nodes(nodes, format, parse_fields_spec("all"), table_style=None, one_line=False, show_header=True, width=None)

@get.command()
@click.argument('ids', required=True)
@click.option(
    "--format",
    type=click.Choice(["node", "csv", "json"]),
    default="node", show_default=True,
    help="Output format"
)
def ids(ids, format):
    """Get information about a node by ID."""
    nodes = get_nodes_by_id(ids)

    if not nodes:
        click.echo("Node not found.")
    else:
        display_nodes(nodes, format, parse_fields_spec("all"), table_style=None, one_line=False, show_header=True, width=None)

@get.command()
@click.argument('ips', required=True)
@click.option(
    "--format",
    type=click.Choice(["node", "csv", "json"]),
    default="node", show_default=True,
    help="Output format"
)
def ips(ips, format):
    """Get information about a node by IP."""
    nodes = get_nodes_by_ip(ips)

    if not nodes:
        click.echo("Node not found.")
    else:
        display_nodes(nodes, format, parse_fields_spec("all"), table_style=None, one_line=False, show_header=True, width=None)

@get.command(name='any')
@click.argument('identifiers')
@click.option(
    "--format",
    type=click.Choice(["node", "csv", "json"]),
    default="node", show_default=True,
    help="Output format"
)
def any_cmd(identifiers, format):
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
        display_nodes(nodes, format, parse_fields_spec("all"), table_style=None, one_line=False, show_header=True, width=None)
