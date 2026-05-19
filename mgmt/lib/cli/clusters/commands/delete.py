
import click
from lib.cli import completion
from lib.logger import logger
from lib.ociwrap import delete_cluster,delete_memory_cluster,delete_compute_cluster
from lib.database import get_nodes_by_cluster, get_clusters, get_nodes_by_memory_cluster
import time

### 
### Add a node to the cluster
###

@click.command()
@click.option('--cluster', required=False, help='Specify the name of the cluster', shell_complete=completion.complete_clusters)
@click.option('--memory_cluster', required=False, help='Specify the ocid of the Memory cluster (Compute cluster does not need to be specified)', shell_complete=completion.complete_memory_clusters)
def delete(cluster,memory_cluster):
    """Delete a cluster with name."""
    if memory_cluster is None:
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
        if node_list[0].memory_cluster_id == 'None' or node_list[0].memory_cluster_id is None:
            logger.debug("Deleting cluster: {}".format(cluster_name))
            delete_cluster(cluster_name,node_list)
        else:
            logger.debug("Deleting memory cluster: {}".format(cluster_name))
            memory_clusters = list({i.memory_cluster_id for i in node_list})
            for memory_cluster in memory_clusters:        
                memory_cluster_node_list = get_nodes_by_memory_cluster(memory_cluster)
                cc_id=delete_memory_cluster(memory_cluster,memory_cluster_node_list)
            time.sleep(120)
            logger.debug("Deleting compute cluster: {}".format(cc_id))
            delete_compute_cluster(cc_id)

    else:
        memory_cluster_node_list = get_nodes_by_memory_cluster(memory_cluster)
        delete_memory_cluster(memory_cluster,memory_cluster_node_list)
