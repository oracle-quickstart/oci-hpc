
import click
from lib.oci import run_boot_volume_swap
from lib.database import get_nodes_by_any
from ClusterShell.NodeSet import NodeSet


### 
### Boot Volume Swap
###

@click.command()
@click.option('--nodes', required=True, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)')
@click.option('--image', required=False, help='Specify the image for BVR')
def boot_volume_swap(nodes,image):
    """Boot Volume Swap nodes"""
    nodes = get_nodes_by_any(NodeSet(nodes))
    
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        for node in nodes:
            run_boot_volume_swap(node,image=image)
    pass