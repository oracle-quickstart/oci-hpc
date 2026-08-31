
import click
from lib.cli import completion
from lib.functions import get_slurm_state, run_command, run_active_hc, run_multi_node_active_hc
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
        nodes_list = db.get_nodes_by_fields(field_dict)
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list


def get_healthcheck_reservation(node, slurm_state, reservation):
    if reservation:
        return reservation

    slurm_node_state = slurm_state.get(node.hostname, {})
    live_reservation = slurm_node_state.get("reservation_id")
    if live_reservation:
        return live_reservation

    return getattr(node, "slurm_reservation", None)


@click.command()
@click.option(
    "--nodes",
    required=False,
    help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)",
    shell_complete=completion.complete_node_identifiers,
)
@click.option(
    '--fields',
    required=False,
    help='Fields to filter nodes (e.g., role=compute,status=running)',
    shell_complete=completion.complete_node_fields,
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
    help="Node to exclude from multi_node healthcheck",
    shell_complete=completion.complete_node_identifiers,
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
    cfg = ctx.obj
    if not nodes_list:
        click.echo("Node not found.")
        return
    slurm_state = get_slurm_state() if type in ("active", "multi-node", "all") and not reservation else {}

    if type == "passive" or type == "all":
        run_command(nodes_list,"sudo /config/bin/uv_wrapper.sh run-venv /opt/oci-hpc/healthchecks/check_gpu_setup.py",print_output=True, clush_parallel_executions=cfg["clush_parallel_executions"])
    for node in nodes_list:
        reservation_id = get_healthcheck_reservation(node, slurm_state, reservation)
        if type=="active" or type == "all":
            run_active_hc(node,reservation_id=reservation_id)
        elif type=="multi-node" or type == "all":
            run_multi_node_active_hc([node],exclude_node=exclude_node,reservation_id=reservation_id)
