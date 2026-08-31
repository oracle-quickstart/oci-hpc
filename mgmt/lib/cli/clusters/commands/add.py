import click
from lib.cli import completion
from lib.cli.clusters.commands.gmf import (
    resolve_cluster_hpc_island,
    resolve_fabric_targets,
    resolve_memory_cluster_name,
    resolve_target_count,
)
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
@click.option('--cluster', required=False, help='Name of the cluster', shell_complete=completion.complete_clusters)
@click.option('--names', required=False, help='Comma-separated list of host names')
@click.option('--memorycluster', required=False, help='OCID of the memory cluster (alternative to --cluster)', shell_complete=completion.complete_memory_clusters)
def node(count, cluster, names, memorycluster):
    """Add compute nodes to a cluster.\n
    Example:\n

    mgmt clusters add node --count 2 --cluster mycluster
    """
    if names:
        name_list = names.split(',')
        if count != len(name_list):
            raise click.ClickException("The number of names does not match the count")
    else:
        name_list = []

    if cluster and memorycluster:
        raise click.ClickException("Use either --cluster or --memorycluster, not both")

    if cluster is None and memorycluster is None:
        clusters = get_clusters()
        if len(clusters) == 1:
            cluster = clusters[0]
            logger.info(f"Using cluster {cluster}.")
        else:
            cluster_string = ", ".join(clusters)
            click.echo("Please specify the cluster in your command with --cluster")
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


    run_add(
        nodes,
        int(count),
        name_list,
        cluster,
        compartment_ocid,
        memory_cluster_ocid=memorycluster,
    )

@add.command()
@click.option('--count', type=int, required=False, help='Number of nodes to add per memory fabric; omit or use 0 with --all or multiple fabrics to use each fabric AVAILABLE count')
@click.option('--cluster', required=True, help='Name of the compute cluster', shell_complete=completion.complete_clusters)
@click.option('--fabric', required=False, help='OCID of the memory fabric, or comma-separated OCIDs of memory fabrics', shell_complete=completion.complete_fabrics)
@click.option('--all', 'all_fabrics', is_flag=True, default=False, help='Add all unused GPU memory fabrics that have AVAILABLE hosts')
@click.option('--compute-local-block-id', required=False, help='Add all unused GPU memory fabrics in this compute local block')
@click.option('--compute-network-block-id', required=False, help='Add all unused GPU memory fabrics in this compute network block')
@click.option('--compute-hpc-island-id', required=False, help='Add all unused GPU memory fabrics in this compute HPC island')
@click.option('--memorycluster', required=False, help='Name for the memory cluster', shell_complete=completion.complete_memory_clusters)
@click.option('--computeclusterocid', required=False, help='OCID of the compute cluster when adding memory cluster to existing compute cluster. By default, looking at all Compute clusters with the cluster name.')
@click.option('--instancetype', required=False, help='Instance type for the nodes; will use one from the existing node if not specified', shell_complete=completion.complete_configurations_compute)
@click.option('--targetsize', type=int, required=False, default=18, help='Target size for the memory cluster, default to 18 if tenancy is whitelisted, use 0 to deactivate')
@click.option('--minimum-gmc-size', '--minimum_gmc_size', 'minimum_gmc_size', type=click.IntRange(min=1), required=False, help='Only use GPU memory fabrics with at least this many AVAILABLE hosts')
@click.option('--dump-command', is_flag=True, default=False, help='Resolve variables and print the equivalent OCI raw-request command without creating the memory cluster')
def memory_fabric(count, cluster, fabric, all_fabrics, compute_local_block_id, compute_network_block_id, compute_hpc_island_id, memorycluster, instancetype, computeclusterocid, targetsize, minimum_gmc_size, dump_command):
    """Add nodes to a memory fabric.\n
  Example:\n

  mgmt clusters add memory-fabric --count 1 --cluster mycluster --fabric
  ocid1.fabric.oc1..xxxx --instancetype BM.GPU.GB200.4

  mgmt clusters add memory-fabric --all --cluster mycluster --instancetype BM.GPU.GB200.4

  mgmt clusters add memory-fabric --all --cluster mycluster --instancetype BM.GPU.GB200.4 --minimum-gmc-size 12
    """
    if cluster is None:
        clusters = get_clusters()
        if len(clusters) == 1:
            cluster = clusters[0]
            logger.info(f"Using cluster {cluster}.")
        else:
            cluster_string = ", ".join(clusters)
            click.echo("Please specify the cluster in your command with --cluster.")
            click.echo(f"Clusters Available: {cluster_string}")
            return

    nodes = get_nodes_by_cluster(cluster)
    if not nodes:
        logger.info("No nodes found in the specified cluster.")
        cluster_hpc_island_id = None
    else:
        cluster_hpc_island_id = resolve_cluster_hpc_island(nodes, cluster)

    scoped_fabrics = bool(compute_local_block_id or compute_network_block_id or compute_hpc_island_id)
    if (all_fabrics or scoped_fabrics) and not cluster_hpc_island_id and not compute_hpc_island_id:
        logger.error(
            f"Could not determine HPC island for cluster {cluster}. "
            "Specify --compute-hpc-island-id."
        )
        return

    config = None
    if instancetype:
        config = get_config_by_name(instancetype)
        if config is None:
            logger.error(f"Instance type {instancetype} not found, exiting")
            return

    if not nodes and not config:
        logger.error("No nodes found in the specified cluster and no instance type specified, exiting")
        return

    if computeclusterocid:
        cc_id=computeclusterocid
    else:
        cc_id=None

    controller=get_controller_node()
    fabric_targets = resolve_fabric_targets(
        controller,
        fabric=fabric,
        all_fabrics=all_fabrics,
        compute_local_block_id=compute_local_block_id,
        compute_network_block_id=compute_network_block_id,
        compute_hpc_island_id=compute_hpc_island_id,
        current_hpc_island_id=cluster_hpc_island_id,
        minimum_gmc_size=minimum_gmc_size,
        cluster=cluster,
    )
    if not fabric_targets:
        logger.error(
            "Specify --fabric with one or more OCIDs, --all, "
            "--compute-local-block-id, --compute-network-block-id, or --compute-hpc-island-id"
        )
        return

    multiple_fabrics = len(fabric_targets) > 1
    for fabric_target in fabric_targets:
        fabric_count = resolve_target_count(count, fabric_target)
        gpu_memory_cluster_name = resolve_memory_cluster_name(
            cluster,
            memorycluster,
            fabric_target["ocid"],
            multiple=multiple_fabrics,
        )
        logger.info(
            f"Adding {fabric_count} node(s) from memory fabric {fabric_target['ocid']} "
            f"as memory cluster {gpu_memory_cluster_name}"
        )
        run_add_memory_fabric(
            nodes,
            controller,
            fabric_count,
            fabric_target["ocid"],
            gpu_memory_cluster_name,
            instancetype=config,
            compute_cluster_id=cc_id,
            compute_cluster_name=cluster,
            targetsize=targetsize,
            dump_command=dump_command,
        )
