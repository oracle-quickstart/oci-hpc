import click
from lib.ociwrap import list_custom_images
from lib.cli.images.display import print_image_list_yaml_json,print_image_list
from lib.database import get_controller_node, get_nodes_with_latest_healthchecks
from lib.logger import logger

@click.command('list')
@click.option(
    "--format",
    type=click.Choice(["tabular", "json","yaml"]),
    default="tabular", show_default=True,
    help="Output format"
)
@click.option('--used', is_flag=True, default=False, show_default=True, help='Only show currently used images.')
@click.option('--compartment', required=False, help='Specify compartment OCID if not controller compartment')
def list_images(format, used, compartment):
    """List Configuration based on role, partition, or shape."""
    if not compartment:
        controller = get_controller_node()
        compartment = controller.compartment_id
    custom_images=list_custom_images(compartment)
    used_custom_images=[]
    if used:
        nodes_per_image={}
        query = get_nodes_with_latest_healthchecks()
        nodes = query.all()
        used_image_ids=[node.image_id for node in nodes]
        unique_used_image_ids = list(set(used_image_ids))
        for image in custom_images:
            if image.id in unique_used_image_ids:
                used_custom_images.append(image)
        for node in nodes:
            if node.image_id in nodes_per_image:
                nodes_per_image[node.image_id].append(node.hostname)
            else:
                nodes_per_image[node.image_id]=[node.hostname]
    else:
        used_custom_images=custom_images
        nodes_per_image=None
    if format=="yaml":
        print_image_list_yaml_json(used_custom_images,type="yaml",nodes_per_image=nodes_per_image)
    elif format=="json":
        print_image_list_yaml_json(used_custom_images,type="json",nodes_per_image=nodes_per_image)
    else:
        print_image_list(used_custom_images,"Custom Images",nodes_per_image=nodes_per_image)