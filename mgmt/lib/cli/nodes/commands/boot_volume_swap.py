
import click
from lib.oci import run_boot_volume_swap, list_custom_images
from lib.database import get_nodes_by_any, db_update_node
from ClusterShell.NodeSet import NodeSet


### 
### Boot Volume Swap
###

@click.command()
@click.option('--nodes', required=True, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)')
@click.option('--image', required=False, help='Specify the image for BVR')
def boot_volume_swap(nodes,image):
    """Boot Volume Swap nodes"""
    nodes = get_nodes_by_any(NodeSet(nodes))
        # In case no image is specified, propose a list of image and ask for the value
    if image is None:
        image_ocid = list_custom_images(nodes[0].compartment_id)
    else:
        image_ocid=image
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        for node in nodes:
            try:
                run_boot_volume_swap(node,image_ocid)
                db_update_node(node,compute_status="starting")
            except Exception as e:
                click.echo(f"Error running boot volume swap for node {node.hostname}: {e}")

    pass