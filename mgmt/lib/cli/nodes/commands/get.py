
import click
from lib.cli.nodes.display import print_nodes_info
from lib.database import get_nodes_by_id, get_nodes_by_serial, get_nodes_by_name, get_nodes_by_ip, get_nodes_by_any
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

@click.group()
def get():
    """Get information about nodes."""
    pass

@get.command()
@click.option('--serials', required=True, help='Serial number of the node.')
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
def serials(serials, full):
    """Get information about a node by serial number."""
    nodes = get_nodes_by_serial(NodeSet(serials))
    
    if not nodes:
        click.echo("node not found.")
        return
    else: 
        print_nodes_info(nodes, full=full)

@get.command()     
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.option('--names', required=True, help='Name of the node.')
def names(names, full):
    """Get information about a node by host name."""
    nodes = get_nodes_by_name(NodeSet(names))
    
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        print_nodes_info(nodes, full=full)

@get.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.option('--ids', required=True, help='ID of the node.')
def ids(ids, full):
    """Get information about a node by ID."""
    nodes = get_nodes_by_id(NodeSet(ids))
    
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        print_nodes_info(nodes, full=full)   

@get.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.option('--ips', required=True, help='IP of the node.')
def ips(ips, full):
    """Get information about a node by IP."""
    nodes = get_nodes_by_ip(NodeSet(ips))
    
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        print_nodes_info(nodes, full=full)

@get.command()
@click.option('--full', is_flag=True, help='Get full information about the node.', default=False)
@click.option('--any', required=True, help='any of the hostname, OCID, IP, serial, OCI_name of the node.')
def any(any, full):
    """Get information about a node by hostname OCID, IP, serial or OCI name."""
    nodes = get_nodes_by_any(NodeSet(any))
    
    if not nodes:
        click.echo("Node not found.")
        return
    else: 
        print_nodes_info(nodes, full=full)

        