import click
from lib.functions import run_command
import lib.database as db
from ClusterShell.NodeSet import NodeSet

from lib.logger import logger

def filter_cmd(ctx, nodes, fields):
    if (not nodes and not fields) or (nodes and fields):
        click.echo("Error: You must specify either --nodes or --fields")
        click.echo()
        click.echo(ctx.get_help())
        ctx.exit(1)

    # If fields are provided, use them to filter nodes
    if fields:
        field_dict = {}
        for field in fields.split(','):
            if '=' not in field:
                raise click.BadParameter(f"Field must be in key=value format: {field}")
            key, value = field.split('=', 1)
            field_dict[key] = value.lower() == 'true' if value.lower() in ['true', 'false'] else value
        nodes_list = db.get_query_by_fields(db.get_nodes_with_latest_healthchecks(),field_dict).all()
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list

@click.command()
@click.option(
    "--nodes",
    required=False,
    help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)"
)
@click.option(
    '--fields',
    required=False,
    help='Fields to filter nodes (e.g., role=compute,status=running)'
)
@click.option(
    '--action',
    type=click.Choice(["compute", "controller", "all", "custom", "command", "ansible"]),
    default="all",
    required=False,
    help='What to reconfigure (compute will rerun the cloud-init, controller will reconfigure the node on the controller (Slurm Topology and Prometheus targets), \n all will reconfigure the node on the controller and the cloud-init, customer will reconfigure the node on the controller and the cloud-init, \n custom will reconfigure the node on the controller and the cloud-init, \n command will run a custom command on the nodes)'
)
@click.option(
    '--command',
    required=False,
    help='Specify the command to run on the nodes. To be used with --action=command'
)
@click.option(
    '--playbook',
    required=False,
    help='Specify the command to run on the nodes. To be used with --action=command'
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
            click.echo("The command will be ignored since the action is not set to command.")
    if action == "ansible":
        if not playbook:
            click.echo("No ansible specified.")
            return
    nodes_list = filter_cmd(ctx,nodes, fields)
    if not nodes_list:
        click.echo("No nodes found.")
        return

    if action == "controller" or action == "all":
        logger.info("Reconfiguring controllers: "+str(NodeSet(','.join([node.hostname for node in nodes_list]))))
        for node in nodes_list:
            db.db_update_node(node, controller_status="reconfiguring")
    if action == "compute" or action == "all":
        command_to_run="sudo bash /var/lib/cloud/instance/scripts/part-001"
        logger.info("Re-running cloud-init on nodes: "+str(NodeSet(','.join([node.hostname for node in nodes_list]))))
        for node in nodes_list:
            db.db_update_node(node, compute_status="starting")
        run_command(nodes_list,command_to_run)
    if action == "custom":
        logger.info("Running Ansible custom role on nodes: "+str(NodeSet(','.join([node.hostname for node in nodes_list]))))
        command_to_run="/config/bin/custom_ansible.sh custom"
        run_command(nodes_list,command_to_run)
    if action == "ansible":
        logger.info(f"Running Ansible role {playbook} on nodes: "+str(NodeSet(','.join([node.hostname for node in nodes_list]))))
        command_to_run=f"/config/bin/custom_ansible.sh {playbook}"
        run_command(nodes_list,command_to_run)
    if action == "command":
        logger.info("Running command on nodes: "+str(NodeSet(','.join([node.hostname for node in nodes_list]))))
        logger.info(f"Running custom command {command} on nodes: "+str(NodeSet(','.join([node.hostname for node in nodes_list]))))
        run_command(nodes_list,command)