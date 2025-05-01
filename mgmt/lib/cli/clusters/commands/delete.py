
import click
from lib.logger import logger
from lib.oci import delete_cluster
from lib.database import get_nodes_by_cluster, get_clusters

### 
### Add a node to the cluster
###

@click.command()
@click.option('--cluster', required=False, help='Specify the name of the cluster')
def delete(cluster):
    """Delete a cluster with name."""
    if cluster is None:
        clusters=get_clusters()
        if len(clusters)==1:
            click.echo(f"Deleting the only cluster found: {clusters[0]}")
            cluster_name=clusters[0]
        else:
            click.echo("More than one cluster found, please use the --cluster option")
            exit(1)            
    else:
        cluster_name=cluster
    node_list = get_nodes_by_cluster(cluster_name)
    delete_cluster(cluster_name,node_list)
    

