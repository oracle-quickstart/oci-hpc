
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
@click.option('--cluster', required=True, help='Specify the name of the cluster')
@click.option('--instancetype', required=True, help='Specify the instance type of the cluster')
@click.option('--names', required=False, help='comma separated list of host names')
def create(count,cluster,instancetype,names):
    """Create a new cluster."""
    if names:
        name_list=names.split(',')
        if count != len(name_list):
            click.echo("The names does not match the count, exiting")
            exit(1)
    else:
        name_list=[]
    config = get_config_by_name(instancetype)
    controller = get_controller_node()
    if controller is None:
        controller_hostname=socket.gethostname()
    else:
        controller_hostname=controller.hostname
    create_cluster(config,int(count),cluster,controller_hostname, name_list)
    

