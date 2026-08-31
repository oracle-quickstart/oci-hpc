
import click
from lib.cli import completion
from lib.ociwrap import run_terminate, run_terminate_no_wait
import lib.database as db
from lib.database import get_controller_node
from ClusterShell.NodeSet import NodeSet
from lib.functions import update_hosts_on_cluster
from lib.logger import logger


def filter_cmd(ctx, nodes, fields, topology_filters=None):
    topology_filters = {
        field: value
        for field, value in (topology_filters or {}).items()
        if value
    }
    selector_count = int(bool(nodes)) + int(bool(fields)) + len(topology_filters)
    if selector_count != 1:
        click.echo("Error: You must specify exactly one node selector")
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
    elif topology_filters:
        nodes_list = db.get_nodes_by_fields(topology_filters)
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list


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


@click.command()
@click.pass_context
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
    '--compute-local-block-id', '--local-block-id', '--local-block', '--localblock',
    'compute_local_block_id',
    required=False,
    help='Terminate all nodes in this compute local block.',
)
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
def terminate(ctx, nodes, fields, compute_local_block_id, force, no_wait):
    """Terminate nodes."""
    nodes_list = filter_cmd(
        ctx,
        nodes,
        fields,
        topology_filters={"rail_id": compute_local_block_id},
    )

    if not nodes_list:
        click.echo("Node not found.")
        return

    memory_clusters = memory_clusters_from_nodes(nodes_list)
    if compute_local_block_id and memory_clusters and not force:
        raise click.ClickException(
            "The selected local block contains node(s) in GPU memory cluster(s): {}. "
            "I think you meant to run mgmt clusters delete --local-block {}. "
            "Re-run with --force to terminate the nodes instead.".format(
                ", ".join(memory_clusters),
                compute_local_block_id,
            )
        )

    for node in nodes_list:
        if is_controller_node(node):
            logger.error(f"Refusing to terminate controller node: {node.hostname}")
            continue
        db.db_update_node(node, status="terminating", controller_status="terminating")
        if no_wait:
            run_terminate_no_wait(node)
        else:
            run_terminate(node)

    cfg = ctx.find_object(dict) or {}
    if cfg.get("manage_hosts"):
        update_hosts_on_cluster(manage_hosts=True, clush_parallel_executions=cfg.get("clush_parallel_executions",10))
