import click
from lib.cli import completion
from lib.cli import click_filter_nodes
from lib.ociwrap import run_boot_volume_swap, pick_custom_images
import lib.database as db
from lib.logger import logger


@click.command()
@click_filter_nodes
@click.option("--image", required=False, help="Specify the image for BVR", shell_complete=completion.complete_images)
@click.option("--size", required=False, help="Specify the size for BVR in GB", type=int)
@click.pass_context
def boot_volume_swap(ctx, nodes, image, size):
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
    # In case no image is specified, propose a list of image and ask for the value
    if image is None:
        compartment_id = None
        for node in nodes:
            if node.compartment_id is not None:
                compartment_id = node.compartment_id
                break
        if compartment_id is None:
            controller = db.get_controller_node()
            compartment_id = controller.compartment_id if controller else None
        try:
            image_ocid = pick_custom_images(compartment_id)
        except ValueError as e:
            raise click.ClickException(str(e))
    else:
        image_ocid = image

    for node in nodes:
        try:
            logger.info(f"Running boot volume swap for {node.hostname or node.ocid}...")
            run_boot_volume_swap(node, image_ocid, size)
            db.db_update_node(node, compute_status="starting")
        except Exception as e:
            logger.error(f"Error running boot volume swap for node {node.hostname}: {e}")
