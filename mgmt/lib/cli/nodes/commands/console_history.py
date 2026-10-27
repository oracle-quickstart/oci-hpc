
import click
from lib.cli import click_filter_nodes
from lib.ociwrap import get_console_history
from lib.logger import logger


@click.command()
@click_filter_nodes
@click.pass_context
def console_history(ctx, nodes):
    """Get console history output for one or more nodes.
    
    You must specify either --nodes or --fields to identify which nodes to reboot.
    
    Example:\n
      #Get console history names\n
      --nodes=node1,node2\n
      #Get console history by fields\n
      --fields=role=compute,status=running
    """
    for node in nodes:
        try:
            console_history = get_console_history(node)
            if console_history is None:
                click.echo(f"No console history found for the node: {node.hostname}")
                return
            
            else: 
                click.echo(f"##### Console history for the node: {node.hostname} #####")
                print(console_history.decode("utf-8"))
        except Exception as exc:
            logger.error(f"Error Getting Console History {node.hostname} with OCID: {node.ocid}: {exc}")
            ctx.exit(1)
    
    
    
