
import click
from lib.logger import logger
from lib.ociwrap import create_login_nodes
from lib.database import get_config_by_name, get_controller_node

import socket
### 
### Add a node to the cluster
###

@click.command()
@click.option('--count', type=int, required=True, help='Number of login nodes to add')
@click.option('--configuration', required=True, help='Specify the name of the login configuration')
@click.option('--names', required=True, help='Comma separated list of host names')
def create(count,configuration,names):
    """Add login node to the cluster."""
    if names:
        name_list=names.split(',')
        if count != len(name_list):
            click.echo("The names does not match the count, exiting")
            exit(1)
    config = get_config_by_name(configuration)
    controller = get_controller_node()
    if controller is None:
        controller_hostname=socket.gethostname()
        cluster_name=controller_hostname.split("-controller")[0]
    else:
        controller_hostname=controller.hostname
        cluster_name=controller.cluster_name
    create_login_nodes(config,int(count),controller_hostname,cluster_name, name_list)
    

