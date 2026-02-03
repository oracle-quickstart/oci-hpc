import click
from lib.logger import logger
from lib.ociwrap import run_add, run_add_memory_fabric
from lib.database import get_controller_node, get_nodes_by_cluster, get_clusters, get_nodes_by_memory_cluster, get_config_by_name

# Create the main command group
@click.group("add")
def add():
    """Add nodes to clusters or memory fabrics.
    
    Available subcommands:\n
      - node: Add compute nodes to a cluster\n
      - memory-fabric: Add nodes to a memory fabric
    """
    pass

@add.command()
@click.option('--count', type=int, required=True, help='Number of nodes to add')
@click.option('--cluster', required=False, help='Name of the cluster')
@click.option('--names', required=False, help='Comma-separated list of host names')
@click.option('--memorycluster', required=False, help='Name of the memory cluster (alternative to --cluster)')
def node(count, cluster, names, memorycluster):
    """Add compute nodes to a cluster.\n
    Example:\n
  
    mgmt clusters add node --count 2 --cluster mycluster
    """
    if names:
        name_list = names.split(',')
        if count != len(name_list):
            click.echo("The number of names does not match the count, exiting")
            exit(1)
    else:
        name_list = []
        
    if cluster is None and memorycluster is None:
        clusters = get_clusters()
        if len(clusters) == 1:
            cluster = clusters[0]
            logger.info(f"Using cluster {cluster}.")
        else:
            cluster_string = ", ".join(clusters)
            click.echo("Please specify the cluster in your command.")
            click.echo(f"Clusters Available: {cluster_string}")
            return
            
    if memorycluster is None:
        nodes = get_nodes_by_cluster(cluster)
    else:
        nodes = get_nodes_by_memory_cluster(memorycluster)
        
    if not nodes:
        if cluster is None:
            logger.error("No nodes found in the specified cluster.")
            return
        else:
            compartment_ocid = get_controller_node().compartment_id
    else:
        compartment_ocid=nodes[0].compartment_id
            
    
    run_add(nodes, int(count), name_list, cluster,compartment_ocid)

@add.command()
@click.option('--count', type=int, required=True, help='Number of nodes to add')
@click.option('--cluster', required=True, help='Name of the compute cluster')
@click.option('--fabric', required=True, help='OCID of the memory fabric')
@click.option('--memorycluster', required=False, help='Name for the memory cluster')
@click.option('--instancetype', required=True, help='Instance type for the nodes')
def memory_fabric(count, cluster, fabric, memorycluster, instancetype):
    """Add nodes to a memory fabric.\n
  Example:\n
  
  mgmt clusters add memory-fabric --count 1 --cluster mycluster --fabric
  ocid1.fabric.oc1..xxxx --instancetype BM.GPU.GB200.4
    """
    if cluster is None:
        clusters = get_clusters()
        if len(clusters) == 1:
            cluster = clusters[0]
            logger.info(f"Using cluster {cluster}.")
        else:
            cluster_string = ", ".join(clusters)
            click.echo("Please specify the cluster in your command.")
            click.echo(f"Clusters Available: {cluster_string}")
            return
            
    nodes = get_nodes_by_cluster(cluster)
    if not nodes:
        logger.error("No nodes found in the specified cluster.")
        return
        
    config = None
    if instancetype:
        config = get_config_by_name(instancetype)
        if config is None:
            logger.error(f"Instance type {instancetype} not found, exiting")
            return
            
    gpu_memory_cluster_name = memorycluster if memorycluster else f"{cluster}_{fabric[-5:]}"
    run_add_memory_fabric(nodes, int(count), fabric, gpu_memory_cluster_name, instancetype=config)
