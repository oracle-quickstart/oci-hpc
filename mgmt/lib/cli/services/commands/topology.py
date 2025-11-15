import click

from lib.database import db_update_node, get_nodes_by_filters, get_controller_node
from lib.functions import run_ansible_slurm_init

@click.command()
def init():
    """Reconfigure the Slurm Config files on the controller. topology.conf ."""

    nodes=get_nodes_by_filters({"role": "compute"})
    for node in nodes:
        db_update_node(node, controller_status="reconfiguring")
    controller = get_controller_node()
    run_ansible_slurm_init(controller.hostname)