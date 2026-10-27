import click
from lib.cli import completion
from lib.cli import click_filter_nodes
from lib.functions import get_slurm_state, run_command, run_active_hc, run_multi_node_active_hc


def get_healthcheck_reservation(node, slurm_state, reservation):
    if reservation:
        return reservation

    slurm_node_state = slurm_state.get(node.hostname, {})
    live_reservation = slurm_node_state.get("reservation_id")
    if live_reservation:
        return live_reservation

    return getattr(node, "slurm_reservation", None)


@click.command()
@click_filter_nodes
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
def healthchecks(ctx, nodes, type, exclude_node, reservation):
    """Run healthchecks on given nodes."""
    cfg = ctx.obj
    slurm_state = get_slurm_state() if type in ("active", "multi-node", "all") and not reservation else {}

    if type == "passive" or type == "all":
        run_command(nodes,"sudo /config/bin/uv_wrapper.sh run-venv /opt/oci-hpc/healthchecks/check_gpu_setup.py",print_output=True, clush_parallel_executions=cfg["clush_parallel_executions"])
    for node in nodes:
        reservation_id = get_healthcheck_reservation(node, slurm_state, reservation)
        if type=="active" or type == "all":
            run_active_hc(node,reservation_id=reservation_id)
        elif type=="multi-node" or type == "all":
            run_multi_node_active_hc([node],exclude_node=exclude_node,reservation_id=reservation_id)
