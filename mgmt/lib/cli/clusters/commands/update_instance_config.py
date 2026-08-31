import click
from lib.cli import completion
import lib.ociwrap as ociwrap
from lib.database import get_nodes_by_cluster, get_nodes_by_memory_cluster
import logging

logger = logging.getLogger(__name__)


@click.command("update-instance-config")
@click.option("--cluster-name", required=False, help="Cluster name from DB", shell_complete=completion.complete_clusters)
@click.option(
    "--memory-cluster",
    required=False,
    help="Compute GPU memory cluster OCID/name to update a single GMC.",
    shell_complete=completion.complete_memory_clusters,
)
@click.option("--image-id", help="New image OCID", shell_complete=completion.complete_images)
@click.option("--ssh-key", help="Override SSH public key")
@click.option("--cloud-init", help="Path to cloud-init file")
@click.option("--boot-volume-size", type=int, help="Override boot volume size (GB)")
@click.option("--display-name", help="New instance configuration display name")
@click.option(
    "--instance-config-id",
    "--instance-configuration-id",
    help="Existing instance configuration OCID to attach to the cluster or GMC instead of creating a new one",
)
@click.option("--bvr", is_flag=True, help="Replace boot volume on existing nodes")
@click.option("--bvr-size", type=int, help="Optional new boot volume size during BVR")
def update_instance_config(
    cluster_name,
    memory_cluster,
    image_id,
    ssh_key,
    cloud_init,
    boot_volume_size,
    display_name,
    instance_config_id,
    bvr,
    bvr_size,
):
    if not cluster_name and not memory_cluster:
        raise click.ClickException("Pass --cluster-name or --memory-cluster")
    create_config_options = [image_id, ssh_key, cloud_init, boot_volume_size, display_name]
    if instance_config_id and any(create_config_options):
        raise click.ClickException(
            "--instance-config-id cannot be combined with --image-id, --ssh-key, "
            "--cloud-init, --boot-volume-size, or --display-name"
        )
    if not instance_config_id and not any(create_config_options):
        raise click.ClickException(
            "Pass --instance-config-id or at least one of --image-id, --ssh-key, "
            "--cloud-init, --boot-volume-size, or --display-name"
        )
    if bvr_size and not bvr:
        raise click.ClickException("--bvr-size requires --bvr")
    if bvr and not image_id:
        raise click.ClickException("--bvr requires --image-id")

    try:
        new_config_id = ociwrap.update_instance_config(
            cluster_name=cluster_name,
            image_id=image_id,
            ssh_key=ssh_key,
            cloud_init_path=cloud_init,
            boot_volume_size=boot_volume_size,
            new_display_name=display_name,
            memory_cluster_id=memory_cluster,
            existing_instance_config_id=instance_config_id,
        )
        click.echo(f"Cluster updated to new config: {new_config_id}")

        if bvr:
            if memory_cluster:
                nodes = get_nodes_by_memory_cluster(memory_cluster)
            else:
                nodes = get_nodes_by_cluster(cluster_name)
            if not nodes:
                raise click.ClickException("No nodes found for cluster")
            if len(nodes) == 1:
                logger.warning("Cluster has only one node. BVR will cause downtime.")

            for node in nodes:
                logger.info(f"Updating node {node.hostname}")
                ociwrap.run_boot_volume_swap(node, image_id, bvr_size)
                logger.info(f"Node {node.hostname} updated")

            logger.info("Cluster BVR complete")

    except Exception as e:
        raise click.ClickException(str(e))
