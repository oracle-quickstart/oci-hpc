import click
from lib.cli.nodes.display import print_nodes_info, print_node_list
from lib.database import list_blocks_by_cluster, get_nodes_by_network_block, get_nodes_by_rail, list_rails_by_cluster
# from click_option_group import optgroup, RequiredMutuallyExclusiveOptionGroup, MutuallyExclusiveOptionGroup

@click.group()
def network():
    """ Network block commands."""
    pass

@network.group()
def blocks():
    """Commands to manage network blocks."""
    pass

@blocks.group()
def list():
    """List commands for blocks."""
    pass

@list.command()
@click.option('--cluster', required=True, help='Name of the cluster.')
def cluster(cluster):
    """ Get blocks by cluster """
    blocks = list_blocks_by_cluster(cluster)
    if not blocks:
        click.echo("No blocks found.")
        return
    else: 
        for block in blocks:
            nodes = get_nodes_by_network_block(block)
            if not nodes:
                click.echo(f"No nodes found in block {block}.")
                continue
            else: 
                click.echo(f"Nodes in Block {block}: {[node.hostname for node in nodes]}")


@network.group()
def rails():
    """Commands to manage rails."""
    pass

@rails.group()
def list():
    """List commands for rails."""
    pass

@list.command()
@click.option('--cluster', required=True, help='Name of the cluster.')
@click.option('--nodes/--no-nodes', is_flag=True, help='Show nodes in the rail.', default=True, type=bool)
def cluster(cluster, nodes):
    """ Get rails by cluster """
    rails = list_rails_by_cluster(cluster)
    if not blocks:
        click.echo("No blocks found.")
        return
    else: 
        for rail in rails:
            if nodes: 
                node_list = get_nodes_by_rail(rail)
                if not node_list:
                    click.echo(f"No nodes found in rail {rail}.")
                    continue
                else: 
                    click.echo(f"Rail {rail} Nodes: {[node.hostname for node in node_list]}")
            else: 
                click.echo(f"Rail {rail}")
            
