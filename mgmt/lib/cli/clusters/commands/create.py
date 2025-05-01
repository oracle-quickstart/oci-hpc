
import click
from lib.logger import logger
from lib.oci import create_cluster
from lib.database import get_config_by_name, get_controller_node

import socket
### 
### Add a node to the cluster
###

@click.command()
@click.option('--count', type=int, required=True, help='Number of nodes to add')
@click.option('--cluster', required=False, help='Specify the name of the cluster')
@click.option('--instancetype', required=False, help='Specify the instance type of the cluster')
def create(count,cluster,instancetype):
    """Create a new cluster."""
    config = get_config_by_name(instancetype)
    controller = get_controller_node()
    if controller is None:
        controller_hostname=socket.gethostname()
    else:
        controller_hostname=controller.hostname
    create_cluster(config,int(count),cluster,controller_hostname)
    

