import click
from lib.cli import click_filter_nodes
from lib.ociwrap import run_stop
import lib.database as db
from lib.logger import logger


@click.command()
@click_filter_nodes
@click.option(
    "--soft",
    is_flag=True,
    help="Perform a soft stop instead of a hard stop"
)
@click.pass_context
def stop(ctx, nodes, soft):
    """Stop one or more nodes.
    
    You must specify either --nodes or --fields to identify which nodes to reboot.
    
    Example:\n
      #Stop by node names\n
      --nodes=node1,node2\n
      #Stop by fields\n
      --fields=role=compute,status=running\n
      #Soft stop\n
      --nodes=node1 --soft
    """
    for node in nodes:
        try:
            logger.info(f"Stopping {node.hostname or node.ocid}...")
            run_stop(node, soft)
            db.db_update_node(node, compute_status="stopped")
        except Exception as exc:
            logger.error(f"Error Stopping {node.hostname or node.ocid}: {exc}")
            ctx.exit(1)
