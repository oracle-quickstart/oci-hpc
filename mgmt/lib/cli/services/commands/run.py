import click

from lib.database import get_all_nodes, get_nodes_by_any, db_update_node,get_controller_node, get_all_nodes_to_configure, db_move_terminated_node, get_nodes_by_active_hc_expired
from lib.functions import get_updates_based_on_url, run_ansible, scan_host_api_logic, get_slurm_state
from lib.ociwrap import oci_scan_queue_and_update_db
from lib.logger import logger
import socket
import subprocess
from datetime import timedelta

# ------------------------
# Shared logic as helpers
# ------------------------

def update_metadata_logic(http_port=9876, nodes=None):
    if nodes:
        node_list = get_nodes_by_any(nodes)
    else:
        node_list = get_all_nodes()
    update_dict = get_updates_based_on_url(node_list, http_port)
    slurm_dict=get_slurm_state()
    for node in node_list:
        if node.hostname in slurm_dict.keys():
            update_dict[node.ocid]["slurm_state"]=slurm_dict[node.hostname]["state"]
            update_dict[node.ocid]["slurm_partition"]=','.join(slurm_dict[node.hostname]["partition"])
        db_update_node(node, **update_dict[node.ocid])

def scan_queue_logic():
    controller = get_controller_node()
    if controller is None:
        controller_hostname = socket.gethostname()
    else:
        controller_hostname = controller.hostname
    oci_scan_queue_and_update_db(controller_hostname)


def ansible_logic():
    controller = get_controller_node()
    nodes_configuring,nodes_terminating = get_all_nodes_to_configure()
    logger.debug("Nodes configuring:"+str(len(nodes_configuring)))
    logger.debug("Nodes terminating:"+str(len(nodes_terminating)))
    if len(nodes_configuring)+len(nodes_terminating):
        ansible_successfull=run_ansible(controller.hostname)
        if ansible_successfull:
            for node in nodes_configuring:
                db_update_node(node,controller_status="configured")
            for node in nodes_terminating:
                logger.info(f"There are {len(nodes_terminating)} nodes terminating that will be moved")
                db_move_terminated_node(node)
    else:
        logger.info("No nodes to configure")

def active_hc_logic():
    active_hc_timeout=timedelta(hours=24)
    nodes=get_nodes_by_active_hc_expired(active_hc_timeout)
    logger.debug(f"Nodes With expired active HC:{len(nodes)}")
    for node in nodes:
        logger.debug(f"Running active healthcheck on {node.hostname}")
        cmd=["sbatch","-N","1","-p","compute","-w",node.hostname,"/opt/oci-hpc/healthchecks/active_HC.sbatch"]        
        subprocess.call(cmd)
    logger.debug("Active healthcheck is done")

# ------------------------
# Click Commands
# ------------------------

@click.group()
def run():
    """Get information about nodes."""
    pass


@run.command()
@click.option('--nodes', required=False, help='any of the hostname, OCID, IP, serial, OCI_name of the node.')
@click.option('--http_port', type=int, required=False, default=9876, help='Specify HTTP Port.')
def update_metadata(nodes, http_port):
    """Update metadata for all hosts in the DB."""
    update_metadata_logic(http_port=http_port, nodes=nodes)


@run.command()
def scan_queue():
    """Scan queue for new or removed nodes and update the DB."""
    scan_queue_logic()


@run.command()
def ansible():
    """Run Ansible to configure nodes."""
    ansible_logic()


@run.command()
def scan_host_api():
    """Scan Host API, update Health information and report number of available nodes in the dedicated pool."""
    available_nodes=scan_host_api_logic()
    for shape in available_nodes.keys():
        click.echo(f"There are {available_nodes[shape]} available nodes of shape {shape} in your pool.")


@run.command()
@click.option('--http_port', type=int, required=False, default=9876, help='Specify HTTP Port.')
def all(http_port):
    """Run full workflow: scan queue, update metadata, run ansible and update nodes in case of success."""
    scan_queue_logic()
    update_metadata_logic(http_port)
    ansible_logic()
    available_nodes=scan_host_api_logic()
    for shape in available_nodes.keys():
        click.echo(f"There are {available_nodes[shape]} available nodes of shape {shape} in your pool.")
    active_hc_logic()

@run.command()
def active_hc():
    """Run active healthcheck."""
    active_hc_logic()