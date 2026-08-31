
import click
from lib.cli import completion
from lib.logger import logger
from lib.ociwrap import (
    delete_cluster,
    delete_memory_cluster,
    delete_compute_cluster,
    resolve_compute_gpu_memory_cluster_delete_targets,
)
from lib.database import get_nodes_by_cluster, get_clusters, get_nodes_by_memory_cluster
import time

### 
### Add a node to the cluster
###

def _validate_option_value(ctx, param, value):
    if value and value.startswith("-"):
        raise click.BadParameter(
            f"{param.opts[0]} requires a value; use '{ctx.command_path} --help' for help"
        )
    return value

def _split_memory_clusters(memory_cluster):
    if memory_cluster is None:
        return []
    return [item.strip() for item in memory_cluster.split(",") if item.strip()]

def _memory_clusters_from_nodes(nodes):
    return sorted({
        node.memory_cluster_id
        for node in nodes
        if node.memory_cluster_id and node.memory_cluster_id != "None"
    })

def _memory_cluster_identifiers(memory_cluster):
    return {
        identifier for identifier in [
            getattr(memory_cluster, "id", None),
            getattr(memory_cluster, "display_name", None),
        ]
        if identifier
    }

def _get_nodes_for_memory_cluster(memory_cluster):
    nodes = get_nodes_by_memory_cluster(memory_cluster.id)
    if not nodes and getattr(memory_cluster, "display_name", None):
        nodes = get_nodes_by_memory_cluster(memory_cluster.display_name)
    return nodes

def _filter_memory_clusters_in_db(memory_clusters):
    filtered_memory_clusters = []
    skipped_memory_clusters = []
    for memory_cluster in memory_clusters:
        if _get_nodes_for_memory_cluster(memory_cluster):
            filtered_memory_clusters.append(memory_cluster)
        else:
            skipped_memory_clusters.append(memory_cluster.display_name or memory_cluster.id)
    if skipped_memory_clusters:
        logger.info(
            "Skipping memory cluster(s) not present in mgmt DB: %s",
            ", ".join(skipped_memory_clusters),
        )
    return filtered_memory_clusters

def _scope_filters(compute_local_block_id, compute_network_block_id, compute_hpc_island_id):
    return {
        "compute_local_block_id": compute_local_block_id,
        "compute_network_block_id": compute_network_block_id,
        "compute_hpc_island_id": compute_hpc_island_id,
    }

def _validate_memory_cluster_selector(memory_cluster, scope_filters):
    selector_count = int(bool(memory_cluster)) + sum(bool(value) for value in scope_filters.values())
    if selector_count <= 1:
        return
    raise click.ClickException(
        "Use only one of --memory_cluster, --compute-local-block-id, "
        "--compute-network-block-id, or --compute-hpc-island-id"
    )

@click.command()
@click.option('--cluster', required=False, callback=_validate_option_value, help='Specify the name of the cluster', shell_complete=completion.complete_clusters)
@click.option('--memory_cluster', required=False, callback=_validate_option_value, help='Specify memory cluster or GPU memory fabric OCID(s), comma-separated', shell_complete=completion.complete_memory_cluster_delete_targets)
@click.option('--compute-local-block-id', '--local-block-id', '--local-block', '--localblock', required=False, help='Delete all compute GPU memory clusters in this compute local block')
@click.option('--compute-network-block-id', '--network-block-id', '--network-block', '--networkblock', required=False, help='Delete all compute GPU memory clusters in this compute network block')
@click.option('--compute-hpc-island-id', '--hpc-island-id', '--hpc-island', required=False, help='Delete all compute GPU memory clusters in this compute HPC island')
@click.option('--force-skip-recycle', is_flag=True, default=False, help='Set GPU memory fabric recycle level to SKIP_RECYCLE before deleting memory cluster(s)')
@click.option('--force-full-recycle', is_flag=True, default=False, help='Set GPU memory fabric recycle level to FULL_RECYCLE before deleting memory cluster(s)')
def delete(cluster,memory_cluster,compute_local_block_id,compute_network_block_id,compute_hpc_island_id,force_skip_recycle,force_full_recycle):
    """Delete a cluster with name."""
    if force_skip_recycle and force_full_recycle:
        raise click.ClickException("Use either --force-skip-recycle or --force-full-recycle, not both")
    scope_filters = _scope_filters(compute_local_block_id, compute_network_block_id, compute_hpc_island_id)
    _validate_memory_cluster_selector(memory_cluster, scope_filters)
    scoped_memory_clusters = any(scope_filters.values())

    recycle_level = None
    if force_skip_recycle:
        recycle_level = "SKIP_RECYCLE"
    elif force_full_recycle:
        recycle_level = "FULL_RECYCLE"

    if memory_cluster is None and not scoped_memory_clusters:
        if cluster is None: 
            clusters=get_clusters()
            if len(clusters)==1:
                click.echo(f"Deleting the only cluster found: {clusters[0]}")
                cluster_name=clusters[0]
            else:
                raise click.ClickException("More than one cluster found, please use the --cluster option")
        else:
            cluster_name=cluster
            
        node_list = get_nodes_by_cluster(cluster_name)
        if node_list[0].memory_cluster_id == 'None' or node_list[0].memory_cluster_id is None:
            logger.debug("Deleting cluster: {}".format(cluster_name))
            delete_cluster(cluster_name,node_list)
        else:
            logger.debug("Deleting memory cluster: {}".format(cluster_name))
            memory_clusters = list({i.memory_cluster_id for i in node_list})
            cc_id = None
            for memory_cluster in memory_clusters:        
                memory_cluster_node_list = get_nodes_by_memory_cluster(memory_cluster)
                deleted_cc_id=delete_memory_cluster(memory_cluster,memory_cluster_node_list,recycle_level=recycle_level)
                if deleted_cc_id is not None:
                    cc_id = deleted_cc_id
            if cc_id is None:
                logger.error("No compute GPU memory clusters could be deleted; skipping compute cluster deletion")
                return
            time.sleep(120)
            logger.debug("Deleting compute cluster: {}".format(cc_id))
            delete_compute_cluster(cc_id)

    else:
        memory_clusters = _split_memory_clusters(memory_cluster)
        if not memory_clusters and not scoped_memory_clusters:
            raise click.ClickException("Please specify at least one memory cluster")
        cluster_node_list = []
        if cluster is not None:
            cluster_node_list = get_nodes_by_cluster(cluster)
            cluster_memory_clusters = _memory_clusters_from_nodes(cluster_node_list)
        resolved_memory_clusters = resolve_compute_gpu_memory_cluster_delete_targets(
            memory_clusters,
            nodes=cluster_node_list,
            **scope_filters,
        )
        if cluster is not None and scoped_memory_clusters:
            cluster_memory_cluster_set = set(cluster_memory_clusters)
            resolved_memory_clusters = [
                memory_cluster for memory_cluster in resolved_memory_clusters
                if _memory_cluster_identifiers(memory_cluster) & cluster_memory_cluster_set
            ]
            if not resolved_memory_clusters:
                raise click.ClickException(
                    "No memory clusters in the requested scope are associated with cluster {}. "
                    "Memory clusters found in cluster: {}".format(
                        cluster,
                        ", ".join(cluster_memory_clusters) or "none",
                    )
                )
        elif cluster is not None:
            missing_memory_clusters = [
                memory_cluster.display_name or memory_cluster.id
                for memory_cluster in resolved_memory_clusters
                if not (_memory_cluster_identifiers(memory_cluster) & set(cluster_memory_clusters))
            ]
            if missing_memory_clusters:
                raise click.ClickException(
                    "Memory cluster(s) {} are not associated with cluster {}. "
                    "Memory clusters found in cluster: {}".format(
                        ", ".join(missing_memory_clusters),
                        cluster,
                        ", ".join(cluster_memory_clusters) or "none",
                    )
                )
        else:
            resolved_memory_clusters = _filter_memory_clusters_in_db(resolved_memory_clusters)
            if not resolved_memory_clusters:
                raise click.ClickException("No requested memory clusters are present in the mgmt DB")
        for memory_cluster in resolved_memory_clusters:
            memory_cluster_node_list = _get_nodes_for_memory_cluster(memory_cluster)
            delete_memory_cluster(memory_cluster.id,memory_cluster_node_list,recycle_level=recycle_level)
