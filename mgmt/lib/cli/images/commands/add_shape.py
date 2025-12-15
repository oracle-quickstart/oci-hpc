import click
from lib.ociwrap import add_shape_to_image
from lib.logger import logger
from lib.database import get_controller_node

@click.command()
@click.option('--image', required=True, help='Image OCID or name of the image to modify')
@click.option('--compartment', required=False, help='Specify compartment OCID if not controller compartment')
@click.option('--shape', required=True, help='Shape to add to the image')

def add_shape(image, compartment,shape):
    """Import image """
    if not compartment:
        controller = get_controller_node()
        compartment = controller.compartment_id
  #  try:
    add_shape_to_image(image, compartment, shape)
  #  except Exception as e:
  #      logger.error(f"Error creating custom image: {e}")
