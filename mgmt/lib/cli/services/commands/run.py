import click
from lib.database import get_all_nodes, get_nodes_by_any, db_update_node,get_controller_node, get_all_nodes_to_configure, db_move_terminated_node
from lib.functions import update_nodes_based_on_url, run_ansible, scan_host_api_logic
from lib.oci import oci_scan_queue, get_host_api_dict
from lib.logger import logger
import socket

# ------------------------
# Shared logic as helpers
# ------------------------

def update_metadata_logic(http_port=9876, nodes=None):
    if nodes:
        node_list = get_nodes_by_any(nodes)
    else:
        node_list = get_all_nodes()
    update_dict = update_nodes_based_on_url(node_list, http_port)
    print(update_dict)
    for node in node_list:
        db_update_node(node, **update_dict[node.ocid])

def scan_queue_logic():
    controller = get_controller_node()
    if controller is None:
        controller_hostname=socket.gethostname()
    else:
        controller_hostname=controller.hostname
    oci_scan_queue(controller_hostname)

def ansible_logic():
    controller = get_controller_node()
    nodes_configuring,nodes_terminating = get_all_nodes_to_configure()
    if len(nodes_configuring)+len(nodes_terminating):
        ansible_successfull=run_ansible(controller.hostname)
        if ansible_successfull:
            for node in nodes_configuring:
                db_update_node(node,controller_status="configured")
            for node in nodes_terminating:  
                logger.info(f"There are {len(nodes_terminating)} nodes terminating that will be moved")              
                db_move_terminated_node(node)
    else:
        logger.warning("No nodes to configure")

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
    """Scan Host API, upodate Health information and report number of available nodes in the dedicated pool."""
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


