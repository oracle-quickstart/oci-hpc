
import click
import lib.database as db
from lib.ociwrap import get_console_history
from lib.logger import logger
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
@click.pass_context
def console_history(ctx, nodes, fields):
    """Get console history output for one or more nodes.
    
    You must specify either --nodes or --fields to identify which nodes to reboot.
    
    Example:\n
      #Get console history names\n
      --nodes=node1,node2\n
      #Get console history by fields\n
      --fields=role=compute,status=running
    """

    nodes_list = filter_cmd(ctx, nodes, fields)
    if not nodes_list:
        logger.warning("No matching nodes found.")
        ctx.exit(1)

    for node in nodes_list:
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
    
    
    

