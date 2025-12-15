import click
from lib.ociwrap import run_boot_volume_swap, pick_custom_images
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
@click.option("--image", required=False, help="Specify the image for BVR")
@click.option("--size", required=False, help="Specify the size for BVR in GB", type=int)
@click.pass_context
def boot_volume_swap(ctx, nodes, fields, image, size):
    """Boot Volume Swap one or more nodes.
    
    You must specify either --nodes or --fields to identify which nodes to reboot.
    
    Example:\n
     #Boot Volume Swap by node names\n
     --nodes=node1,node2\n
     #Boot Volume Swap by fields\n
     --fields=role=compute,status=running\n
     #Boot Volume Swap image\n
     --image=ocid1.image.oc1..exampleuniqueid\n
     #Boot Volume Swap BV size\n 
     --size=100\n
    """

    nodes_list = filter_cmd(ctx, nodes, fields)
        # In case no image is specified, propose a list of image and ask for the value
    if image is None:
        if nodes_list:
            compartment_id = nodes_list[0].compartment_id
        else:
            controller = db.get_controller_node()
            compartment_id = controller.compartment_id

        image_ocid = pick_custom_images(compartment_id)
    else:
        image_ocid = image

    if not nodes_list:
        logger.warning("No matching nodes found.")
        ctx.exit(1)

    for node in nodes_list:
        try:
            run_boot_volume_swap(node, image_ocid, size)
            db.db_update_node(node, compute_status="starting")
        except Exception as e:
            logger.error(f"Error running boot volume swap for node {node.hostname}: {e}")
