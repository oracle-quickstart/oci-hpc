
import click
from lib.logger import logger
from lib.ociwrap import delete_cluster,delete_memory_cluster,delete_compute_cluster
from lib.database import get_nodes_by_cluster, get_clusters, get_nodes_by_memory_cluster, get_controller_node
import time

### 
### Add a node to the cluster
###

@click.command()
@click.option('--cluster', required=False, help='Specify the name of the cluster')
@click.option('--memory_cluster', required=False, help='Specify the name of the Memory cluster (Compute cluster does not need to be specified)')
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
        if node_list[0].memory_cluster_name == 'None' or node_list[0].memory_cluster_name is None:
            logger.debug("Deleting cluster: {}".format(cluster_name))
            delete_cluster(cluster_name,node_list)
        else:
            logger.debug("Deleting memory cluster: {}".format(cluster_name))
            memory_clusters = list({i.memory_cluster_name for i in node_list})
            for memory_cluster in memory_clusters:        
                memory_cluster_node_list = get_nodes_by_memory_cluster(memory_cluster)
                if not memory_cluster_node_list:
                    controller = get_controller_node()
                    compartment_id=controller.compartment_id
                else:
                    compartment_id=memory_cluster_node_list[0].compartment_id
                cc_id=delete_memory_cluster(memory_cluster,memory_cluster_node_list,compartment_id)
            time.sleep(120)
            logger.debug("Deleting compute cluster: {}".format(cc_id))
            delete_compute_cluster(cc_id)

    else:
        memory_cluster_node_list = get_nodes_by_memory_cluster(memory_cluster)
        if not memory_cluster_node_list:
            controller = get_controller_node()
            compartment_id=controller.compartment_id
        else:
            compartment_id=memory_cluster_node_list[0].compartment_id
        delete_memory_cluster(memory_cluster,memory_cluster_node_list,compartment_id)
