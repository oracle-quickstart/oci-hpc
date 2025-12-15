
import click
from lib.functions import run_command, run_active_hc, run_multi_node_active_hc
import lib.database as db
from ClusterShell.NodeSet import NodeSet

from lib.logger import logger

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
        nodes_list = db.get_query_by_fields(db.get_nodes_with_latest_healthchecks(),field_dict).all()
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list

@click.command()
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
@click.option(
    "--type",
    type=click.Choice(["all", "passive", "active", "multi-node"]),
    default="passive",
    required=False,
    help="Type of healthcheck to run (all, passive, active, multi-node). Active healthchecks will "
        + "write results to /var/log/healthchecks"
)
@click.option(
    "--exclude-node",
    required=False,
    help="Node to exclude from multi_node healthcheck"
)
@click.option(
    "--reservation",
    required=False,
    help="Include a Reservation Name for the healthcheck in case the nodes are in a reservation, "
        + "InitialValidation is the reservation created for all new nodes. "
)
@click.pass_context
def healthchecks(ctx, nodes, fields, type, exclude_node, reservation):
    """Run healthchecks on given nodes."""
    nodes_list = filter_cmd(ctx, nodes, fields)

    if not nodes_list:
        click.echo("Node not found.")
        return

    if type == "passive" or type == "all":
        run_command(nodes_list,"sudo python3 /opt/oci-hpc/healthchecks/check_gpu_setup.py",print_output=True)
    for node in nodes_list:
        if type=="active" or type == "all":
            run_active_hc(node,reservation_id=reservation)
        elif type=="multi-node" or type == "all":
            run_multi_node_active_hc([node],exclude_node=exclude_node,reservation_id=reservation)
