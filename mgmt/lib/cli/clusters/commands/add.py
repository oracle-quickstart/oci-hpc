
import click
from lib.logger import logger
from lib.oci import run_add
from lib.database import get_nodes_by_cluster, get_clusters

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
def add(count, cluster, names):
    """Replace the image of nodes by serial number."""
    if names:
        name_list=names.split(',')
        if count != len(name_list):
            click.echo("The names does not match the count, exiting")
            exit(1)
    else:
        name_list=[]
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
    if not nodes:
        logger.error("Node not found.")
        return
    else: 
        run_add(nodes, int(count), name_list)