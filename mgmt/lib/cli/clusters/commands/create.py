
import click
from lib.cli import completion
from lib.cli.clusters.commands.gmf import resolve_fabric_targets, resolve_memory_cluster_name, resolve_target_count
from lib.logger import logger
from lib.ociwrap import create_cluster
from lib.database import get_clusters, get_config_by_name, get_controller_node


import socket
###
### Add a node to the cluster
###

@click.command()
@click.option('--count', type=int, required=False, help='Number of nodes to add; omit or use 0 with --all or multiple fabrics to use each fabric AVAILABLE count')
@click.option('--cluster', required=True, help='Specify the name of the cluster', shell_complete=completion.complete_clusters)
@click.option('--instancetype', required=True, help='Specify the instance type of the cluster', shell_complete=completion.complete_configurations_compute)
@click.option('--names', required=False, help='comma separated list of host names')
@click.option('--fabric', required=False, help='OCID of the memory fabric, or comma-separated OCIDs of memory fabrics for GMF based nodes', shell_complete=completion.complete_fabrics)
@click.option('--all', 'all_fabrics', is_flag=True, default=False, help='Use all unused GPU memory fabrics that have AVAILABLE hosts')
@click.option('--compute-local-block-id', required=False, help='Use all unused GPU memory fabrics in this compute local block')
@click.option('--compute-network-block-id', required=False, help='Use all unused GPU memory fabrics in this compute network block')
@click.option('--compute-hpc-island-id', required=False, help='Use all unused GPU memory fabrics in this compute HPC island')
@click.option('--memorycluster', required=False, help='Name used for the memory cluster, default will be cluster_xxxxx with xxxxx the last 5 character of the fabric ocid', shell_complete=completion.complete_memory_clusters)
@click.option('--targetsize', type=int, required=False, default=0, help='Target size for the memory cluster scale config, use 0 to deactivate')
@click.option('--minimum-gmc-size', type=click.IntRange(min=1), required=False, help='Only use GPU memory fabrics with at least this many AVAILABLE hosts')
def create(count, cluster, instancetype, names, fabric, all_fabrics, compute_local_block_id, compute_network_block_id, compute_hpc_island_id, memorycluster, targetsize, minimum_gmc_size):
    """Create a new cluster.\n
    Example:\n
    # Create a standard compute cluster\n

    mgmt clusters create --count 3 --cluster mycluster --instancetype BM.Standard.E3.128\n

    # Create a GPU cluster with memory fabric\n

    mgmt clusters create --count 2 --cluster mycluster --instancetype BM.GPU.GB200.4 --fabric ocid1.fabric.oc1..xxxx --targetsize 18
    --names node01,node02\n
    mgmt clusters create --cluster mycluster --instancetype BM.GPU.GB300.4 --all --minimum-gmc-size 12\n"""
    if names:
        name_list=names.split(',')
        if count is not None and count != len(name_list):
            raise click.ClickException("The names does not match the count")
    else:
        name_list=[]
    config = get_config_by_name(instancetype)
    if config is None:
        raise click.ClickException(f"Instance type {instancetype} not found. Run `mgmt configurations list` to see available instance types.")
    controller = get_controller_node()
    if controller is None:
        controller_hostname=socket.gethostname()
    else:
        controller_hostname=controller.hostname
    is_gmf_shape = "GPU.GB" in config.shape
    scoped_fabrics = bool(compute_local_block_id or compute_network_block_id or compute_hpc_island_id)
    if (fabric or all_fabrics or scoped_fabrics or minimum_gmc_size) and not is_gmf_shape:
        raise click.ClickException(
            "--fabric, --all, fabric scope options, and --minimum-gmc-size can only be used with GPU memory fabric shapes"
        )
    if count is None and not is_gmf_shape:
        raise click.ClickException("--count is required when creating a non-GMF cluster")

    fabric_targets = []
    if is_gmf_shape:
        if fabric or all_fabrics or scoped_fabrics:
            fabric_targets = resolve_fabric_targets(
                controller,
                fabric=fabric,
                all_fabrics=all_fabrics,
                compute_local_block_id=compute_local_block_id,
                compute_network_block_id=compute_network_block_id,
                compute_hpc_island_id=compute_hpc_island_id,
                require_single_hpc_island=True,
                minimum_gmc_size=minimum_gmc_size,
                cluster=cluster,
            )
        else:
            fabric_targets = resolve_fabric_targets(
                controller,
                all_fabrics=True,
                minimum_gmc_size=minimum_gmc_size,
            )[:1]

    gpu_memory_fabrics = []
    multiple_fabrics = len(fabric_targets) > 1
    for fabric_target in fabric_targets:
        fabric_count = resolve_target_count(count, fabric_target)
        gpu_memory_fabrics.append({
            "ocid": fabric_target["ocid"],
            "count": fabric_count,
            "name": resolve_memory_cluster_name(
                cluster,
                memorycluster,
                fabric_target["ocid"],
                multiple=multiple_fabrics,
            ),
            "targetsize": targetsize,
        })

    clusters = get_clusters()
    if cluster in clusters:
        if not gpu_memory_fabrics:
            raise click.ClickException(f"Cluster {cluster} already exists")
        else:
            raise click.ClickException(
                f"Cluster {cluster} already exists, I think you meant to run "
                f"mgmt clusters add memory-fabric --cluster {cluster}"
            )
    if not gpu_memory_fabrics:
        logger.info(f"Creating cluster {cluster} with {count} nodes")
    else:
        fabric_summary = ", ".join(
            f"{item['ocid']} ({item['count']} node(s), {item['name']})"
            for item in gpu_memory_fabrics
        )
        logger.info(f"Creating cluster {cluster} on memory fabric(s): {fabric_summary}")
    create_cluster(
        config,
        int(count or 0),
        cluster,
        controller_hostname,
        name_list,
        gpu_memory_fabrics=gpu_memory_fabrics or None,
        targetsize=targetsize,
    )
