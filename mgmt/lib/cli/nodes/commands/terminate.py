import click
from lib.oci import run_terminate
from lib.database import get_nodes_by_any
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

### 
### Terminate
###

@click.command()
@click.option('--nodes', required=True, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)')
def terminate(nodes):
    """Terminate nodes."""
    nodes = get_nodes_by_any(NodeSet(nodes))
    
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        for node in nodes:
            run_terminate(node)
    pass