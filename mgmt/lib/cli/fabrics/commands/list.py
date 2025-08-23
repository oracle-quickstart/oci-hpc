import click
from lib.database import get_controller_node
from lib.logger import logger
from lib.ociwrap import get_memory_fabrics
from lib.cli.fabrics.display import print_fabrics

@click.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def list(full):
    """List all fabrics for nodes."""

    tenancy = get_controller_node().tenancy_id
    fabric_list=get_memory_fabrics(tenancy,get_controller_node().compartment_id)
    print_fabrics(fabric_list,full)



