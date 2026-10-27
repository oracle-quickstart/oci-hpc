
import click
from lib.cli import click_filter_nodes
from lib.ociwrap import run_tag, run_terminate

import lib.database as db
from lib.database import get_controller_node
from lib.functions import update_hosts_on_cluster
from lib.logger import logger


def is_controller_node(node):
    controller = get_controller_node()
    if controller is None:
        return False

    return node.ocid and node.ocid == controller.ocid

@click.command()
@click_filter_nodes
@click.pass_context
def tag_and_terminate(ctx, nodes):
    """Tag and Terminate nodes."""
    for node in nodes:
        if is_controller_node(node):
            logger.error(f"Refusing to tag and terminate controller node: {node.hostname}")
            continue
        db.db_update_node(node, status="terminating", controller_status="terminating")
        run_tag(node)
        run_terminate(node)

    cfg = ctx.find_object(dict) or {}
    if cfg.get("manage_hosts"):
        update_hosts_on_cluster(manage_hosts=True, clush_parallel_executions=cfg.get("clush_parallel_executions",10))
