
import click

from lib.ociwrap import run_boot_volume_swap, list_custom_images
from lib.database import get_nodes_by_any, db_update_node, get_controller_node


@click.command()
@click.option("--nodes", required=True, help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)")
@click.option("--image", required=False, help="Specify the image for BVR")
@click.option("--size", required=False, help="Specify the size for BVR in GB", type=int)
def boot_volume_swap(nodes, image, size):
    """Boot Volume Swap nodes"""

    nodes = get_nodes_by_any(nodes)
    # In case no image is specified, propose a list of image and ask for the value
    if image is None:
        if nodes:
            compartment_id = nodes[0].compartment_id
        else:
            controller = get_controller_node()
            compartment_id = controller.compartment_id

        image_ocid = list_custom_images(compartment_id)
    else:
        image_ocid = image

    if not nodes:
        click.echo("Node not found.")
        return

    for node in nodes:
        try:
            run_boot_volume_swap(node, image_ocid, size)
            db_update_node(node, compute_status="starting")
        except Exception as e:
            click.echo(f"Error running boot volume swap for node {node.hostname}: {e}")
