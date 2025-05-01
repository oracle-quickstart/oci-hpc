import click
from lib.cli.nodes.display import print_node_list
from lib.database import get_all_nodes, get_nodes_by_cluster, get_all_terminated_nodes, get_all_compute_nodes
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

@click.group(name='list')
def list():
    """List commands for nodes."""
    pass

@list.command()       
@click.option('--one_line', is_flag=True, show_default=True, default=False, help='Share a hostname list in one line') 
@click.option('--include_management', is_flag=True, show_default=True, default=False, help='Include management nodes (controller,login,monitoring)') 
def all(one_line,include_management):
    """Get information about a node by serial number."""
    if include_terminated:
        terminated_nodes=get_all_terminated_nodes()
    if include_management:
        nodes = get_all_nodes()
    else:
        nodes = get_all_compute_nodes()
    if include_terminated:
        nodes+=get_all_terminated_nodes()
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        click.echo(one_line)
        if one_line:
            click.echo(NodeSet(','.join([node.hostname for node in nodes])))
        else:
            print_node_list(nodes, title="All Nodes")
        
@list.command()
@click.option('--cluster', required=True, help='Name of the cluster.')
@click.option('--one_line', is_flag=True, show_default=True, default=False, help='Share a hostname list in one line')
def cluster(cluster,one_line):
    """Get information about a node by cluster name."""
    nodes = get_nodes_by_cluster(cluster)  
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        if one_line:
            click.echo(NodeSet(','.join([node.hostname for node in nodes])))
        else:
            print_node_list(nodes, title="All Nodes")   