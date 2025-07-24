
import click
from lib.logger import logger
from lib.oci import run_add, run_add_memory_fabric
from lib.database import get_nodes_by_cluster, get_clusters, get_nodes_by_memory_cluster, get_config_by_name

### 
### Add a node to the cluster
###


@click.group()
def add():
    """Add a node to the cluster."""
    pass

@add.command()
@click.option('--count', type=int, required=True, help='Number of nodes to add')
@click.option('--cluster', required=False, help='Specify the name of the cluster')
@click.option('--names', required=False, help='comma separated list of host names')
@click.option('--memorycluster', required=False, help='Name of the memory cluster to add the nodes in, cluster name is not required if memory cluster is specified')
def add_node(count, cluster, names, memorycluster):
    """Add additional compute hosts to an existing cluster."""
    if names:
        name_list=names.split(',')
        if count != len(name_list):
            click.echo("The names does not match the count, exiting")
            exit(1)
    else:
        name_list=[]
    if cluster is None and memorycluster is None:
        clusters = get_clusters()
        if len(clusters) == 1:
            cluster=clusters[0]
            logger.info(f"Using cluster {cluster}.")
        else:
            cluster_string=", ".join(clusters)
            click.echo("Please specify the cluster in your command.")
            click.echo(f"Clusters Available: {cluster_string}")
    if memorycluster is None:
        nodes = get_nodes_by_cluster(cluster)
    else:
        nodes = get_nodes_by_memory_cluster(memorycluster)
    if not nodes:
        logger.error("Node not found.")
        return
    else: 
        run_add(nodes, int(count), name_list)

@add.command()
@click.option('--count', type=int, required=True, help='Number of nodes to add in the new memory fabric')
@click.option('--cluster', required=False, help='Specify the name of the compute cluster')
@click.option('--fabric', required=False, help='OCID of the memory fabric to add the nodes in')
@click.option('--memorycluster', required=False, help='Name of the memory cluster to add the nodes in, cluster name is not required if memory cluster is specified')
@click.option('--instancetype', required=True, help='Specify the instance type of the cluster')

def add_memory_fabric(count, cluster, fabric ,memorycluster,instancetype):
    """Add hosts from a memoryfabric to an existing cluster."""
    if cluster is None:
        clusters = get_clusters()
        if len(clusters) == 1:
            cluster=clusters[0]
            logger.info(f"Using cluster {cluster}.")
        else:
            cluster_string=", ".join(clusters)
            click.echo("Please specify the cluster in your command.")
            click.echo(f"Clusters Available: {cluster_string}")
    nodes = get_nodes_by_cluster(cluster)
    if not instancetype is None:
        config = get_config_by_name(instancetype)
        if config is None:
            logger.error(f"Instance type {instancetype} not found, exiting")
            return
    else:
        config=None
    if not nodes:
        logger.error("No node found, create a new cluster instead")
        return
    else: 
        run_add_memory_fabric(nodes, int(count), fabric ,memorycluster, instancetype=config)
