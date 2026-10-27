import click
from lib.cli import click_filter_nodes
from lib.ociwrap import run_reboot
import lib.database as db
from lib.logger import logger


@click.command()
@click_filter_nodes
@click.option(
    "--soft",
    is_flag=True,
    help="Perform a soft reboot (OS level) instead of a hard reset"
)
@click.pass_context
def reboot(ctx, nodes, soft):
    """Reboot one or more nodes.
    
    You must specify either --nodes or --fields to identify which nodes to reboot.
    
    Example:\n
      #Reboot by node names\n
      --nodes=node1,node2\n
      #Reboot by fields\n
      --fields=role=compute,status=running\n
      #Soft reboot\n
      --nodes=node1 --soft
    """
    for node in nodes:
        try:
            logger.info(f"Rebooting {node.hostname or node.ocid}...")
            run_reboot(node, soft)
            db.db_update_node(node, compute_status="starting")
        except Exception as exc:
            logger.error(f"Error rebooting {node.hostname or node.ocid}: {exc}")
            ctx.exit(1)
