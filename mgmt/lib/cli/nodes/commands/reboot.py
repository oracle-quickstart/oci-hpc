
import click
from lib.ociwrap import run_reboot
import lib.database as db
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
@click.option(
    "--soft",
    is_flag=True,
    help="Perform a soft reboot (OS level) instead of a hard reset"
)
@click.pass_context
def reboot(ctx, nodes, fields, soft):
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

    nodes_list = filter_cmd(ctx, nodes, fields)
    if not nodes_list:
        logger.warning("No matching nodes found.")
        ctx.exit(1)

    for node in nodes_list:
        try:
            logger.info(f"Rebooting {node.hostname or node.ocid}...")
            run_reboot(node, soft)
            db.db_update_node(node, compute_status="starting")
        except Exception as exc:
            logger.error(f"Error rebooting {node.hostname or node.ocid}: {exc}")
            ctx.exit(1)
