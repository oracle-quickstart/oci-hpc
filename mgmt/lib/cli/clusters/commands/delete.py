
import click
from lib.logger import logger
from lib.oci import delete_cluster
from lib.database import get_nodes_by_cluster, get_clusters, get_nodes_by_memory_cluster

### 
### Add a node to the cluster
###

@click.command()
@click.option('--cluster', required=False, help='Specify the name of the cluster')
@click.option('--memorycluster', required=False, help='Specify the name of the Memory cluster (Compute cluster does not need to be specified)')
def delete(cluster,memorycluster):
    """Delete a cluster with name."""
    if memorycluster is None:
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

    else:
        node_list = get_nodes_by_memory_cluster(memorycluster)
        delete_cluster(memorycluster,node_list)
