import click
from lib.ociwrap import import_custom_image
from lib.logger import logger
from lib.database import get_controller_node

@click.command()
@click.option('--url', required=True, help='URL of the image to import')
@click.option('--compartment', required=False, help='Specify compartment OCID if not controller compartment')

def create(url, compartment):
    """Import image """
    if not compartment:
        controller = get_controller_node()
        compartment = controller.compartment_id
    try:
        import_custom_image(url, compartment)
    except Exception as e:
        logger.error(f"Error creating custom image: {e}")