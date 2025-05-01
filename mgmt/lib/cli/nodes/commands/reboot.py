
import click
from lib.oci import run_reboot
from lib.database import get_nodes_by_any
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

### 
### Reboot
###

@click.command()
@click.option('--nodes', required=True, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)')
@click.option('--soft', required=True, default=True, help='Soft Reboot the node, default is Force Reboot')

def reboot(nodes,soft):
    """Reboot nodes"""
    nodes = get_nodes_by_any(NodeSet(nodes))
    
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        for node in nodes:
            run_reboot(node,soft)
    pass