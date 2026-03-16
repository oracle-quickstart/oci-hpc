import click
import lib.ociwrap as ociwrap
from lib.database import get_nodes_by_cluster
import logging

logger = logging.getLogger(__name__)


@click.command("update-instance-config")
@click.option("--cluster-name", required=True, help="Cluster name from DB")
@click.option("--image-id", required=True, help="New image OCID")
@click.option("--ssh-key", help="Override SSH public key")
@click.option("--cloud-init", help="Path to cloud-init file")
@click.option("--boot-volume-size", type=int, help="Override boot volume size (GB)")
@click.option("--display-name", help="New instance configuration display name")
@click.option("--bvr", is_flag=True, help="Replace boot volume on existing nodes")
@click.option("--bvr-size", type=int, help="Optional new boot volume size during BVR")
def update_instance_config(
    cluster_name,
    image_id,
    ssh_key,
    cloud_init,
    boot_volume_size,
    display_name,
    bvr,
    bvr_size,
):
    if bvr_size and not bvr:
        raise click.ClickException("--bvr-size requires --bvr")

    try:
        new_config_id = ociwrap.update_instance_config(
            cluster_name=cluster_name,
            image_id=image_id,
            ssh_key=ssh_key,
            cloud_init_path=cloud_init,
            boot_volume_size=boot_volume_size,
            new_display_name=display_name,
        )
        click.echo(f"Cluster updated to new config: {new_config_id}")

        if bvr:
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