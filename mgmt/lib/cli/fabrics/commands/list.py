import click
from lib.database import get_controller_node
from lib.ociwrap import get_memory_fabrics
from lib.cli.fabrics.display import print_fabrics

@click.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.option(
    '--rack-state',
    '--filter',
    'rack_state',
    type=click.Choice(['AVAILABLE', 'UNAVAILABLE', 'OCCUPIED'], case_sensitive=False),
    help='Only show fabrics with racks in this state.',
)
def list(full, rack_state):
    """List all fabrics for nodes."""

    controller = get_controller_node()
    fabric_list=get_memory_fabrics(controller.tenancy_id, controller.compartment_id)
    if rack_state:
        rack_state = rack_state.upper()
        fabric_list = [
            fabric for fabric in fabric_list
            if int(fabric[3].get(rack_state, 0) or 0) > 0
        ]
    print_fabrics(fabric_list, full)
