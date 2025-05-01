import click
from lib.cli.nodes.display import print_node_list, print_node_list_json, print_nodes_info
from lib.database import get_all_nodes, get_nodes_by_cluster, get_all_terminated_nodes, get_all_compute_nodes, get_all_management_nodes
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

@click.group(name='list')
def list():
    """List commands for nodes."""
    pass

@list.command()       
@click.option('--one_line', is_flag=True, show_default=True, default=False, help='Share the hostnames list in one line') 
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def all(one_line,full):
    """List all nodes."""
    nodes = get_all_nodes()
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        if one_line:
            click.echo(NodeSet(','.join([node.hostname for node in nodes])))
        else:
            if full:
                print_nodes_info(nodes, full=full)
            else:
                print_node_list(nodes, title="All Nodes")

@list.command()       
@click.option('--one_line', is_flag=True, show_default=True, default=False, help='Share the hostnames list in one line') 
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def compute(one_line,full):
    """List all compute nodes."""
    nodes = get_all_compute_nodes()
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        if one_line:
            click.echo(NodeSet(','.join([node.hostname for node in nodes])))
        else:
            if full:
                print_nodes_info(nodes, full=full)
            else:
                print_node_list(nodes, title="Compute Nodes")

@list.command()       
@click.option('--one_line', is_flag=True, show_default=True, default=False, help='Share the hostnames list in one line') 
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def management(one_line,full):
    """List all management nodes (controller, login, monitoring,...)."""
    nodes=get_all_management_nodes()
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        if one_line:
            click.echo(NodeSet(','.join([node.hostname for node in nodes])))
        else:
            if full:
                print_nodes_info(nodes, full=full)
            else:
                print_node_list(nodes, title="All Nodes")

@list.command()       
@click.option('--one_line', is_flag=True, show_default=True, default=False, help='Share the hostnames list in one line') 
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def terminated(one_line,full):
    """List all terminated nodes."""
    nodes=get_all_terminated_nodes()
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        if one_line:
            click.echo(NodeSet(','.join([node.hostname for node in nodes])))
        else:
            if full:
                print_nodes_info(nodes, full=full)
            else:            
                print_node_list(nodes, title="All Nodes")


@list.command()
@click.option('--cluster', required=True, help='Name of the cluster.')
@click.option('--one_line', is_flag=True, show_default=True, default=False, help='Share a hostname list in one line')
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def cluster(cluster,one_line,full):
    """Get information about nodes in a cluster."""
    nodes = get_nodes_by_cluster(cluster)  
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        if one_line:
            click.echo(NodeSet(','.join([node.hostname for node in nodes])))
        else:
            if full:
                print_nodes_info(nodes, full=full)
            else:
                print_node_list(nodes, title="All Nodes")   

@list.command()       
def json():
    """Show all hosts in json format."""
    nodes = get_all_nodes()
    if not nodes:
        click.echo("No nodes found.")
        return
    else: 
        print_node_list_json(nodes)