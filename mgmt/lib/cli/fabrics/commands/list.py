import click
from lib.database import get_controller_node
from lib.logger import logger
from lib.oci import get_memory_fabrics

@click.command()
def list():
    """List all fabrics for nodes."""

    tenancy = get_controller_node().tenancy_id
    get_memory_fabrics(tenancy)


