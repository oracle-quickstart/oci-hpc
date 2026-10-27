import subprocess
import textwrap
from collections import defaultdict
from time import sleep

import click
import lib.database as db
from ClusterShell.NodeSet import NodeSet
from lib.cli import click_filter_nodes
from lib.functions import (
    delete_nodes_from_slurm,
    get_slurm_state,
    remove_nodes_from_reservation,
    run_command,
)
from lib.logger import logger
from lib.ociwrap import run_enable_instance_rdma_plugins
from lib.versions import dr_hpc_version


@click.command()
@click_filter_nodes
@click.option(
    "--action",
    type=click.Choice(
        [
            "compute",
            "controller",
            "all",
            "custom",
            "command",
            "ansible",
            "install-lfs",
            "dr-hpc",
            "slurm-reinit",
            "metadata",
            "localdisk-recover",
            "localdisk-raid0",
            "localdisk-raid10",
            "enable-instance-rdma-plugins"
        ]
    ),
    default="all",
    required=False,
    help=textwrap.dedent(
        """\
        What to reconfigure:

        compute will rerun the cloud-init on the nodes.

        controller will reconfigure the nodes on the controller (Slurm Topology and
        Prometheus targets).

        all will perform both the controller and compute actions.

        command will run a custom command on the nodes (requires --comand).

        custom will execute the custom Ansible playbook on the nodes.

        ansible will execute an Ansible playbook on the nodes (requires --playbook).

        install-lfs will build and install the Lustre client on the nodes using
        the shared /config/3rdparty artifact path.

        dr-hpc will install or update the DR HPC package on compute nodes. Use
        --version to select a specific version; otherwise resolve latest.json.
        Both update the shared versions.yaml pin before running Ansible.

        metadata will execute a metadata update on the nodes.  May require a SLURM
        topology reconfiguration on the controller to fully take effect.

        slurm-reinit will remove the nodes from SLURM on the controller and restart
        SLURM on the nodes.

        enable-instance-rdma-plugins will enable the OCI Compute RDMA instance plugins on the
        nodes (Compute HPC RDMA Authentication and Compute HPC RDMA Auto-Configuration).

        All the following actions will destroy data on /mnt/localdisk:
        localdisk-recover will recover a failed /mnt/localdisk by recreating the RAID0 array and reformatting it. 
        localdisk-raid0 will recreate the /mnt/localdisk as a RAID0 array, which is the default configuration.
        localdisk-raid10 will recreate the /mnt/localdisk as a RAID10 array, which provides redundancy at the cost of usable capacity.
        """
    ),
)
@click.option(
    "--command",
    required=False,
    help="Specify the command to run on the nodes. To be used with --action=command",
)
@click.option(
    "--playbook",
    required=False,
    help="Specify the playbook to run on the nodes. To be used with --action=ansible",
)
@click.option(
    "--version",
    required=False,
    help="Persist a DR HPC version in versions.yaml before reconfiguring; otherwise use latest. For --action=dr-hpc.",
)

@click.pass_obj
@click.pass_context
def reconfigure(ctx, cfg, nodes, action, command, playbook, version):
    """Rerun the cloud-init script on the nodes."""
    if action == "command":
        if not command:
            click.echo("No command specified.")
            return
    else:
        if command:
            click.echo(
                "The command will be ignored since the action is not set to command."
            )
    if action == "ansible":
        if not playbook:
            click.echo("No ansible specified.")
            return
    if action != "dr-hpc" and version:
        click.echo(
            "The version will be ignored since the action is not set to dr-hpc."
        )

    nodeset = str(NodeSet(",".join([node.hostname for node in nodes])))

    if action in ("controller", "all"):
        logger.info("Reconfiguring controllers: %s", nodeset)
        for node in nodes:
            db.db_update_node(node, controller_status="reconfiguring")
    if action in ("compute", "all"):
        command_to_run = "sudo bash /var/lib/cloud/instance/scripts/part-001"
        logger.info("Re-running cloud-init on nodes: %s", nodeset)
        for node in nodes:
            db.db_update_node(node, compute_status="starting")
        run_command(nodes, command_to_run, clush_parallel_executions=cfg["clush_parallel_executions"])
    if action == "custom":
        logger.info("Running Ansible custom role on nodes: %s", nodeset)
        command_to_run = "/config/bin/custom_ansible.sh custom"
        run_command(nodes, command_to_run, clush_parallel_executions=cfg["clush_parallel_executions"])
    if action == "ansible":
        logger.info("Running Ansible playbook '%s' on nodes: %s", playbook, nodeset)
        command_to_run = f"/config/bin/custom_ansible.sh {playbook}"
        run_command(nodes, command_to_run, clush_parallel_executions=cfg["clush_parallel_executions"])
    if action == "install-lfs":
        logger.info("Running Lustre install workflow on nodes: %s", nodeset)
        command_to_run = "/config/bin/custom_ansible.sh lustre_install"
        run_command(nodes, command_to_run, clush_parallel_executions=cfg["clush_parallel_executions"])
    if action == "dr-hpc":
        non_compute_nodes = [node.hostname for node in nodes if node.role != "compute"]
        if non_compute_nodes:
            logger.error(
                "dr-hpc reconfigure action is only supported on compute nodes. Invalid targets: %s",
                ",".join(non_compute_nodes),
            )
            return
        command_to_run = "/config/bin/custom_ansible.sh dr_hpc"
        try:
            with dr_hpc_version(version) as selected_version:
                logger.info(f"Pinned shared Dr HPC version {selected_version}; reconfiguring nodes: {nodeset}")
                run_command(nodes, command_to_run, clush_parallel_executions=cfg["clush_parallel_executions"])
        except (OSError, ValueError) as error:
            raise click.ClickException(f"Dr HPC reconfiguration failed: {error}") from None
    if action == "command":
        logger.info("Running custom command '%s' on nodes: %s", command, nodeset)
        run_command(nodes, command, clush_parallel_executions=cfg["clush_parallel_executions"])
    if action == "metadata":
        logger.info("Updating metadata on nodes: %s", nodeset)
        run_command(nodes, "/config/bin/custom_ansible.sh metadata", clush_parallel_executions=cfg["clush_parallel_executions"])
        logger.info("Waiting 60 seconds for metadata to be updated...")
        sleep(60)
        logger.info("Reconfiguring controller to update slurm topology: %s", nodeset)
        for node in nodes:
            db.db_update_node(node, controller_status="reconfiguring")
        logger.info(
            "This will be reconfigured at the next run of ansible on the controller."
        )
    if action == "slurm-reinit":
        logger.info("Re-initializing SLURM on nodes: %s", nodeset)
        slurm_state = get_slurm_state()
        reservation_modifications = defaultdict(list)
        slurm_nodes = []
        missing_slurm_nodes = []
        for node in nodes:
            node_slurm_state = slurm_state.get(node.hostname)
            if node_slurm_state is None:
                missing_slurm_nodes.append(node.hostname)
                continue
            slurm_nodes.append(node)
            reservation = node_slurm_state.get("reservation_id")
            if reservation:
                reservation_modifications[reservation].append(node)
        if missing_slurm_nodes:
            logger.info(
                "Nodes not currently registered in SLURM will skip deletion and be restarted: %s",
                NodeSet(",".join(missing_slurm_nodes)),
            )
        for reservation, reserved_nodes in reservation_modifications.items():
            remove_nodes_from_reservation(reserved_nodes, reservation)
        delete_nodes_from_slurm(slurm_nodes)
        command_to_run = " && ".join(
            [
                "sudo systemctl stop slurmd",
                "sudo rm -r /var/spool/slurmd/*",
                "sudo systemctl restart slurmd",
            ]
        )
        run_command(nodes, command_to_run, clush_parallel_executions=cfg["clush_parallel_executions"])
        logger.debug("Reconfiguring Slurm")
        sleep(10)
        reconfigure=subprocess.run(["sudo","scontrol","reconfigure"])
    if action == "enable-instance-rdma-plugins":
        logger.info("Enabling RDMA instance plugins on nodes: %s", nodeset)
        for node in nodes:
            run_enable_instance_rdma_plugins(node)
    if action in ["localdisk-recover", "localdisk-raid0", "localdisk-raid10"]:
        nodeset_str = str(NodeSet(','.join([node.hostname for node in nodes])))
        if action == "localdisk-recover":
            logger.info(f"Recovering /mnt/localdisk on nodes: {nodeset_str}")
            logger.warning("This will destroy all data on the local NVMe drives!")
            run_command(nodes, "/config/bin/custom_ansible.sh recover_localdisk")
        elif action == "localdisk-raid0":
            logger.info(f"Recreating /mnt/localdisk as RAID0 on nodes: {nodeset_str}")
            logger.warning("This will destroy all data on the local NVMe drives!")
            run_command(nodes, "/config/bin/custom_ansible.sh recover_localdisk -e redundancy=false -e force_recovery=true")
        elif action == "localdisk-raid10":
            logger.info(f"Recreating /mnt/localdisk as RAID10 on nodes: {nodeset_str}")
            logger.warning("This will destroy all data on the local NVMe drives!")
            run_command(nodes, "/config/bin/custom_ansible.sh recover_localdisk -e redundancy=true -e force_recovery=true")        
