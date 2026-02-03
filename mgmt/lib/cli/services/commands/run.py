import click

from lib.database import get_all_nodes, get_nodes_by_any, db_update_node,get_controller_node, get_all_nodes_to_configure, db_move_terminated_node, get_nodes_by_active_hc_expired, get_nodes_by_multi_node_hc_expired, get_nodes_for_initial_multi_node_check, get_nodes_validated
from lib.functions import get_updates_based_on_url, run_ansible, scan_host_api_logic, get_slurm_state, append_to_healthchecks, run_multi_node_active_hc, run_active_hc, remove_reservation
from lib.ociwrap import oci_scan_queue_and_update_db
from lib.logger import logger
import socket
import subprocess
from datetime import timedelta
import random

# ------------------------
# Shared logic as helpers
# ------------------------

def update_metadata_logic(http_port=9876, nodes=None):
    if nodes:
        node_list = get_nodes_by_any(nodes)
    else:
        node_list = get_all_nodes()
    update_dict = get_updates_based_on_url(node_list, http_port,"info")
    hc_update_dict = get_updates_based_on_url(node_list, http_port, "healthchecks")
    logger.debug(f"{update_dict}")
    logger.debug(f"{hc_update_dict}")
    #TODO ADD Slurm drain state change
    slurm_dict=get_slurm_state()
    for node in node_list:
        if node.hostname in slurm_dict.keys():
            update_dict[node.ocid]["slurm_state"]=slurm_dict[node.hostname]["state"]
            update_dict[node.ocid]["slurm_partition"]=','.join(slurm_dict[node.hostname]["partition"])
            update_dict[node.ocid]["slurm_reservation"]=slurm_dict[node.hostname]["reservation_id"]
            update_dict[node.ocid]["slurm_up_time"]=slurm_dict[node.hostname]["slurm_up_time"]
        else:
            if node.role == "compute":
                update_dict[node.ocid]["slurm_state"]="unconfigured"
        db_update_node(node, **update_dict[node.ocid])
        logger.debug(f"Node {node.ocid} is not {hc_update_dict.keys()}")
        if node.ocid in hc_update_dict.keys() and hc_update_dict[node.ocid] != {}:
            logger.debug(f"Updating healthchecks for {node.hostname}")
            append_to_healthchecks(node.ocid, **hc_update_dict[node.ocid])


def scan_queue_logic():
    controller = get_controller_node()
    if controller is None:
        controller_hostname = socket.gethostname()
    else:
        controller_hostname = controller.hostname
    oci_scan_queue_and_update_db(controller_hostname)


def ansible_logic():
    controller = get_controller_node()
    if controller is None:
        controller_hostname = socket.gethostname()
    else:
        controller_hostname = controller.hostname
    nodes_configuring,nodes_terminating = get_all_nodes_to_configure()
    logger.debug("Nodes configuring:"+str(len(nodes_configuring)))
    logger.debug("Nodes terminating:"+str(len(nodes_terminating)))
    if len(nodes_configuring)+len(nodes_terminating):
        ansible_successfull=run_ansible(controller_hostname)
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
    nodes_idle,nodes_starting=get_nodes_by_active_hc_expired(active_hc_timeout)
    
    logger.debug(f"Nodes With expired active HC:{len(nodes_idle)}")
    if nodes_idle:
        node=random.choice(nodes_idle)
        run_active_hc(node)
    else:
        logger.debug("No nodes with expired active HC and idle in Slurm")
    if nodes_starting:
        for node in nodes_starting:
            run_active_hc(node,reservation_id=node.slurm_reservation)

def multi_node_hc_logic():
    multi_node_hc_timeout=timedelta(hours=24)
    nodes_healthy, nodes_potentially_bad =get_nodes_by_multi_node_hc_expired(multi_node_hc_timeout)
    logger.debug(f"Nodes With expired Healthy multi node HC:{len(nodes_healthy)}")    
    logger.debug(f"Nodes With Potentially bad multi node HC:{len(nodes_potentially_bad)}")
    if nodes_healthy:
        node=random.choice(nodes_healthy)
        run_multi_node_active_hc([node])
    if nodes_potentially_bad:
        for node in nodes_potentially_bad:
            run_multi_node_active_hc([node],exclude_node=node.multi_node_healthcheck_associated_node)
    if len(nodes_healthy)+len(nodes_potentially_bad)==0:
        logger.debug("No nodes with expired active HC and idle in Slurm")

    nodes_healthy_resv, nodes_potentially_bad_resv =get_nodes_for_initial_multi_node_check(multi_node_hc_timeout)
    for node,index in enumerate(nodes_potentially_bad_resv):
        if nodes_healthy_resv:
            healthy_index=index % len(nodes_healthy_resv)
            run_multi_node_active_hc([node,nodes_healthy_resv[healthy_index]],reservation_id=node.slurm_reservation)
    if nodes_healthy_resv:
        if len(nodes_healthy_resv) % 2 == 0:
            logger.debug(len(nodes_healthy_resv)/2)
            number_pairs=int(len(nodes_healthy_resv)/2)
            logger.debug(number_pairs)
            for i in range(number_pairs):
                run_multi_node_active_hc([nodes_healthy_resv[2*i],nodes_healthy_resv[2*i+1]],reservation_id=nodes_healthy_resv[2*i].slurm_reservation)
        else:
            logger.debug((len(nodes_healthy_resv)-1)/2)
            number_pairs=int((len(nodes_healthy_resv)-1)/2)
            logger.debug(number_pairs)
            for i in range(number_pairs):
                run_multi_node_active_hc([nodes_healthy_resv[2*i],nodes_healthy_resv[2*i+1]],reservation_id=nodes_healthy_resv[2*i].slurm_reservation)
            run_multi_node_active_hc([nodes_healthy_resv[-1]],reservation_id=nodes_healthy_resv[-1].slurm_reservation)
    
def validated_nodes_logic():
    validated_nodes =get_nodes_validated()
    logger.debug(f"Count after validated nodes: {validated_nodes.count()}")
    if validated_nodes.count():
        remove_reservation(validated_nodes.all())
    else:
        logger.debug("No validated nodes found")



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
    logger.debug("Running active healthcheck")
    active_hc_logic()
    logger.debug("Running multi node healthcheck")
    multi_node_hc_logic()
    logger.debug("Running validated nodes logic")
    validated_nodes_logic()

@run.command()
def active_hc():
    """Run active healthcheck."""
    active_hc_logic()

@run.command()
def multi_node_hc():
    """Run active healthcheck."""
    multi_node_hc_logic()

@run.command()
def validated_nodes():
    """Remove the reservation on the validated node."""
    validated_nodes_logic()