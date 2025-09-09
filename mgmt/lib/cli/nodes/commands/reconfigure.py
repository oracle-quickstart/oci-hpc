import click
from lib.functions import run_configure
import lib.database as db
from ClusterShell.NodeSet import NodeSet
def filter_cmd(ctx, nodes, fields):
    if (not nodes and not fields) or (nodes and fields):
        click.echo("Error: You must specify either --nodes or --fields")
        click.echo()
        click.echo(ctx.get_help())
        ctx.exit(1)

    # If fields are provided, use them to filter nodes
    if fields:
        field_dict = {}
        for field in fields.split(','):
            if '=' not in field:
                raise click.BadParameter(f"Field must be in key=value format: {field}")
            key, value = field.split('=', 1)
            field_dict[key] = value.lower() == 'true' if value.lower() in ['true', 'false'] else value
        nodes_list = [node_tuple[0] for node_tuple in nodes_tuple_list]
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list

@click.group()
def reconfigure():
    """List commands for nodes."""
    pass


@reconfigure.command()
@click.option(
    "--nodes",
    required=False,
    help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)"
)
@click.option(
    '--fields',
    required=False,
    help='Fields to filter nodes (e.g., role=compute,status=running)'
)
@click.pass_context
def controller(ctx, nodes, fields):
    """Switch the configure flag in the DB to reconfigure the node on the controller."""
    nodes_list = filter_cmd(ctx, nodes, fields)
    if not nodes_list:
        click.echo("No nodes found.")
        return

    for node in nodes_list:
        db.db_update_node(node, controller_status="reconfiguring")


@reconfigure.command()
@click.option(
    "--nodes",
    required=False,
    help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)"
)
@click.option(
    '--fields',
    required=False,
    help='Fields to filter nodes (e.g., role=compute,status=running)'
)
@click.pass_context
def compute(ctx, nodes, fields):
    """Rerun the cloud-init script on the nodes."""
    nodes_list = filter_cmd(ctx,nodes, fields)
    if not nodes_list:
        click.echo("No nodes found.")
        return

    run_configure(nodes_list)
    for node in nodes_list:
        db.db_update_node(node, compute_status="starting")
