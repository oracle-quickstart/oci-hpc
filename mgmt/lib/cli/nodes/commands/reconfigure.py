from collections import defaultdict
import click
from lib.functions import (
    get_slurm_state,
    delete_nodes_from_slurm,
    remove_nodes_from_reservation,
    run_command,
)
import lib.database as db
from ClusterShell.NodeSet import NodeSet

from lib.logger import logger
import textwrap
from time import sleep


def filter_cmd(ctx, nodes, fields):
    if (not nodes and not fields) or (nodes and fields):
        click.echo("Error: You must specify either --nodes or --fields")
        click.echo()
        click.echo(ctx.get_help())
        ctx.exit(1)

    # If fields are provided, use them to filter nodes
    if fields:
        field_dict = {}
        for field in fields.split(","):
            if "=" not in field:
                raise click.BadParameter(f"Field must be in key=value format: {field}")
            key, value = field.split("=", 1)
            field_dict[key] = (
                value.lower() == "true" if value.lower() in ["true", "false"] else value
            )
        nodes_list = db.get_query_by_fields(
            db.get_nodes_with_latest_healthchecks(), field_dict
        ).all()
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list


@click.command()
@click.option(
    "--nodes",
    required=False,
    help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)",
)
@click.option(
    "--fields",
    required=False,
    help="Fields to filter nodes (e.g., role=compute,status=running)",
)
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
            "slurm-reinit",
            "metadata",
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

        metadata will execute a metadata update on the nodes.  May require a SLURM
        topology reconfiguration on the controller to fully take effect.

        slurm-reinit will remove the nodes from SLURM on the controller and restart
        SLURM on the nodes.
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
@click.pass_context
def reconfigure(ctx, nodes, fields, action, command, playbook):
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
    nodes_list = filter_cmd(ctx, nodes, fields)
    if not nodes_list:
        click.echo("No nodes found.")
        return

    nodeset = str(NodeSet(",".join([node.hostname for node in nodes_list])))

    if action in ("controller", "all"):
        logger.info("Reconfiguring controllers: %s", nodeset)
        for node in nodes_list:
            db.db_update_node(node, controller_status="reconfiguring")
    if action in ("compute", "all"):
        command_to_run = "sudo bash /var/lib/cloud/instance/scripts/part-001"
        logger.info("Re-running cloud-init on nodes: %s", nodeset)
        for node in nodes_list:
            db.db_update_node(node, compute_status="starting")
        run_command(nodes_list, command_to_run)
    if action == "custom":
        logger.info("Running Ansible custom role on nodes: %s", nodeset)
        command_to_run = "/config/bin/custom_ansible.sh custom"
        run_command(nodes_list, command_to_run)
    if action == "ansible":
        logger.info("Running Ansible playbook '%s' on nodes: %s", playbook, nodeset)
        command_to_run = f"/config/bin/custom_ansible.sh {playbook}"
        run_command(nodes_list, command_to_run)
    if action == "command":
        logger.info("Running custom command '%s' on nodes: %s", command, nodeset)
        run_command(nodes_list, command)
    if action == "metadata":
        logger.info("Updating metadata on nodes: %s", nodeset)
        run_command(nodes_list, "/config/bin/custom_ansible.sh metadata")
        logger.info("Waiting 60 seconds for metadata to be updated...")
        sleep(60)
        logger.info("Reconfiguring controller to update slurm topology: %s", nodeset)
        for node in nodes_list:
            db.db_update_node(node, controller_status="reconfiguring")
        logger.info(
            "This will be reconfigured at the next run of ansible on the controller."
        )
    if action == "slurm-reinit":
        logger.info("Re-initializing SLURM on nodes: %s", nodeset)
        slurm_state = get_slurm_state()
        reservation_modifications = defaultdict(list)
        for node in nodes_list:
            reservation = slurm_state[node.hostname].get("reservation_id")
            if reservation:
                reservation_modifications[reservation].append(node)
        for reservation, nodes in reservation_modifications.items():
            remove_nodes_from_reservation(nodes, reservation)
        delete_nodes_from_slurm(nodes_list)
        command_to_run = " && ".join(
            [
                "sudo systemctl stop slurmd",
                "sudo rm -r /var/spool/slurmd/*",
                "sudo systemctl restart slurmd",
            ]
        )
        run_command(nodes_list, command_to_run)
