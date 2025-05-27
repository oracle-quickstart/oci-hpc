import click
from lib.cli.configurations.display import print_config_list_yaml_json,print_config_list
from lib.database import get_config_by_shape_and_partition, get_config_by_shape, get_config_by_partition, get_all_configs
from lib.logger import logger
from lib.oci import get_memory_fabrics
from ClusterShell.NodeSet import NodeSet

@click.command()
def list():
    """List all fabrics for nodes."""
    get_memory_fabrics()

