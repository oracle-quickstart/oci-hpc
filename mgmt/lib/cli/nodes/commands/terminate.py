import click
from lib.cli import click_filter_nodes
from lib.ociwrap import run_terminate, run_terminate_no_wait
import lib.database as db
from lib.database import get_controller_node
from lib.functions import update_hosts_on_cluster
from lib.logger import logger


def is_controller_node(node):
    controller = get_controller_node()
    if controller is None:
        return False

    return node.ocid and node.ocid == controller.ocid


def memory_clusters_from_nodes(nodes):
    return sorted({
        node.memory_cluster_id
        for node in nodes
        if node.memory_cluster_id and node.memory_cluster_id != "None"
    })


def nodes_to_wait_for_gmc_termination(nodes):
    """Return one final node per GMC when this command empties that GMC.

    Individual instance termination is normally submitted asynchronously.  A
    synchronous waiter is only useful when every still-active node in a GPU
    memory cluster is part of this request: the final request provides a
    completion point for a caller that will subsequently delete that GMC.
    """
    selected_node_ocids = {
        node.ocid
        for node in nodes
        if getattr(node, "ocid", None)
    }
    wait_node_ocids = set()

    for memory_cluster_id in memory_clusters_from_nodes(nodes):
        active_gmc_nodes = [
            node
            for node in db.get_nodes_by_memory_cluster(memory_cluster_id)
            if getattr(node, "status", None) not in ("terminating", "terminated")
            and getattr(node, "ocid", None)
        ]
        active_gmc_node_ocids = {node.ocid for node in active_gmc_nodes}
        if not active_gmc_node_ocids or not active_gmc_node_ocids.issubset(selected_node_ocids):
            continue

        # Preserve the caller's ordering and wait only for the final selected
        # node in this GMC after all preceding nodes have been submitted.
        final_node = next(
            (
                node
                for node in reversed(nodes)
                if node.memory_cluster_id == memory_cluster_id
                and node.ocid in active_gmc_node_ocids
            ),
            None,
        )
        if final_node:
            wait_node_ocids.add(final_node.ocid)

    return wait_node_ocids


@click.command()
@click.pass_context
@click_filter_nodes(local_block=True)
@click.option(
    '--force',
    is_flag=True,
    default=False,
    help='Allow terminating nodes in GPU memory clusters selected by --local-block.',
)
@click.option(
    '--no-wait',
    is_flag=True,
    hidden=True,
    help='Submit OCI termination requests without waiting for completion.'
)
def terminate(ctx, nodes, compute_local_block_id, force, no_wait):
    """Terminate nodes."""
    memory_clusters = memory_clusters_from_nodes(nodes)
    if compute_local_block_id and memory_clusters and not force:
        raise click.ClickException(
            "The selected local block contains node(s) in GPU memory cluster(s): {}. "
            "I think you meant to run mgmt clusters delete --local-block {}. "
            "Re-run with --force to terminate the nodes instead.".format(
                ", ".join(memory_clusters),
                compute_local_block_id,
            )
        )

    wait_node_ocids = set() if no_wait else nodes_to_wait_for_gmc_termination(nodes)
    if wait_node_ocids:
        logger.info(
            "Submitting node terminations asynchronously; waiting only for the final node in each fully selected GPU memory cluster."
        )
    elif not no_wait:
        logger.info("Submitting node terminations asynchronously; no selected GPU memory cluster is being emptied.")

    nodes_to_terminate = []
    for node in nodes:
        if is_controller_node(node):
            logger.error(f"Refusing to terminate controller node: {node.hostname}")
            continue
        db.db_update_node(node, status="terminating", controller_status="terminating")
        nodes_to_terminate.append(node)

    # Submit every independent request before waiting. This avoids serial
    # 10-minute waiters and ensures the reserved GMC node is truly last.
    for node in nodes_to_terminate:
        if node.ocid not in wait_node_ocids:
            run_terminate_no_wait(node)

    for node in nodes_to_terminate:
        if node.ocid in wait_node_ocids:
            run_terminate(node)

    cfg = ctx.find_object(dict) or {}
    if cfg.get("manage_hosts"):
        update_hosts_on_cluster(manage_hosts=True, clush_parallel_executions=cfg.get("clush_parallel_executions",10))
