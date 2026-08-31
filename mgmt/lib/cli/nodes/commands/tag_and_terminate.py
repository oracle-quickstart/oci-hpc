
import click
from lib.cli import completion
from lib.ociwrap import run_tag, run_terminate

import lib.database as db
from lib.database import get_controller_node
from ClusterShell.NodeSet import NodeSet
from lib.functions import update_hosts_on_cluster
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
        nodes_list = db.get_nodes_by_fields(field_dict)
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list


def is_controller_node(node):
    controller = get_controller_node()
    if controller is None:
        return False

    return node.ocid and node.ocid == controller.ocid

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
def tag_and_terminate(ctx, nodes, fields):
    """Tag and Terminate nodes."""
    nodes_list = filter_cmd(ctx, nodes, fields)

    if not nodes_list:
        click.echo("Node not found.")
        return

    for node in nodes_list:
        if is_controller_node(node):
            logger.error(f"Refusing to tag and terminate controller node: {node.hostname}")
            continue
        db.db_update_node(node, status="terminating", controller_status="terminating")
        run_tag(node)
        run_terminate(node)

    cfg = ctx.find_object(dict) or {}
    if cfg.get("manage_hosts"):
        update_hosts_on_cluster(manage_hosts=True, clush_parallel_executions=cfg.get("clush_parallel_executions",10))
