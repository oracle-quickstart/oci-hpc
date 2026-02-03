import click
from lib.database import get_all_nodes_failing_to_start, get_all_nodes_with_hc_status, get_all_nodes_unreachable, get_nodes_slurm_unconfigured, join_nodes_lists
from lib.functions import run_configure, scan_host_api_logic, run_reset_gpus
from lib.ociwrap import run_reboot, run_terminate, run_tag
from lib.cli.recommendations.display import print_node_list


from lib.logger import logger
import socket
from datetime import datetime, timedelta, timezone

from ClusterShell.NodeSet import NodeSet

# ------------------------
# Click Commands
# ------------------------

@click.group()
def recom():
    """Get information about nodes."""
    pass

@recom.command()     
@click.option('--healthcheck', is_flag=True, help='Only show the Healthcheck Recommendations.', default=False)
@click.option('--unreachable', is_flag=True, help='Only show the unreachable nodes.', default=False)
@click.option('--unconfigured', is_flag=True, help='Only show the nodes failing to start.', default=False)
@click.option('--unreachable_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=30)
@click.option('--unconfigured_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=60)
def list(unreachable, unconfigured, healthcheck, unreachable_timeout, unconfigured_timeout):
    """List all the nodes with recommendations."""
    unreachable_nodes=[]
    unconfigured_nodes=[]
    nodes_to_reboot=[]
    nodes_to_terminate=[]
    nodes_to_reset_GPUs=[]
    
    if unreachable or not (unreachable or unconfigured or healthcheck):
        unreachable_nodes=get_all_nodes_unreachable(timedelta(minutes=unreachable_timeout),[])
    if unconfigured or not (unreachable or unconfigured or healthcheck):
        nodes_failing_to_start=get_all_nodes_failing_to_start(timedelta(minutes=unconfigured_timeout),[])
        unconfigured_slurm_nodes=get_nodes_slurm_unconfigured()
        unconfigured_nodes=join_nodes_lists(nodes_failing_to_start,unconfigured_slurm_nodes)
    if healthcheck or not (unreachable or unconfigured or healthcheck):
        nodes_to_reboot = get_all_nodes_with_hc_status("Reboot",[])
        nodes_to_reset_GPUs = get_all_nodes_with_hc_status("Reset_GPU",[])
        nodes_to_terminate = get_all_nodes_with_hc_status("Terminate",[])
    # Print tables 
    if unreachable_nodes+nodes_to_reboot:
        print_node_list(unreachable_nodes+nodes_to_reboot, "Nodes to Reboot")
        click.echo(NodeSet(','.join([node.hostname for node in unreachable_nodes+nodes_to_reboot])))
    elif nodes_to_reset_GPUs:
        print_node_list(nodes_to_reset_GPUs, "Nodes to Reset GPUs")
        click.echo(NodeSet(','.join([node.hostname for node in nodes_to_reset_GPUs])))
    else:
        logger.info("All the nodes are Reachable and There are no Unhealthy nodes requiring reboot or GPU reset\n")
    if nodes_to_terminate:
        print_node_list(nodes_to_terminate, "Nodes to Terminate")
        click.echo(NodeSet(','.join([node.hostname for node in nodes_to_terminate])))
    else:
        logger.info("There are no Unhealthy nodes requiring Termination\n")
    if unconfigured_nodes:
        print_node_list(unconfigured_nodes, "Nodes to Reconfigure")
        click.echo(NodeSet(','.join([node.hostname for node in unconfigured_nodes])))
    else:
        logger.info("There are no nodes in need of reconfiguration\n")

    # Print Information about what to run
    if unreachable_nodes or nodes_to_reboot or nodes_to_terminate or unconfigured_nodes:
        click.echo("Running \"mgmt recommendations run\" will run the recommandations listed\n")

    available_nodes=scan_host_api_logic()
    if not available_nodes:
        logger.info("There are no available nodes in the dedicated pool\n")
    for shape in available_nodes.keys():
        click.echo(f"There are {available_nodes[shape]} available nodes of shape {shape} in your pool. running the recommandations will not add the nodes\n")
    

@recom.command()
@click.option('--nodes', required=False, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)')
@click.option('--healthcheck', is_flag=True, help='', default=False)
@click.option('--unreachable', is_flag=True, help='Get full information about the nodes.', default=False)
@click.option('--unconfigured', is_flag=True, help='Get full information about the nodes.', default=False)
@click.option('--unreachable_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=30)
@click.option('--unconfigured_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=60)
def run(unreachable, unconfigured, healthcheck,nodes,unreachable_timeout,unconfigured_timeout):
    """Run all the recommendations."""
    unreachable_nodes=[]
    unconfigured_nodes=[]
    nodes_to_reboot=[]
    nodes_to_terminate=[]
    nodes_to_reset_GPUs=[]
    if not nodes:
        nodes=[]
    if unreachable or not (unreachable or unconfigured or healthcheck):
        unreachable_nodes=get_all_nodes_unreachable(timedelta(minutes=unreachable_timeout),nodes)
    if unconfigured or not (unreachable or unconfigured or healthcheck):
        nodes_failing_to_start=get_all_nodes_failing_to_start(timedelta(minutes=unconfigured_timeout),[])
        unconfigured_slurm_nodes=get_nodes_slurm_unconfigured()
        unconfigured_nodes=join_nodes_lists(nodes_failing_to_start,unconfigured_slurm_nodes)
    if healthcheck or not (unreachable or unconfigured or healthcheck):
        nodes_to_reboot = get_all_nodes_with_hc_status("Reboot",nodes)
        nodes_to_reset_GPUs = get_all_nodes_with_hc_status("Reset_GPU",nodes)
        nodes_to_terminate = get_all_nodes_with_hc_status("Terminate",nodes)
    
    # Reboot unreachable nodes as well as nodes flagged for reboot by Healthcheck. 
    if unreachable_nodes+nodes_to_reboot:
        click.echo("Rebooting: "+str(NodeSet(','.join([node.hostname for node in unreachable_nodes+nodes_to_reboot]))))
        for node in unreachable_nodes+nodes_to_reboot:
            if node.slurm_state=="drain" or node.slurm_state=="down":
                run_reboot(node,False)
            else:
                click.echo(f"Node is not drained, cannot reboot {node.hostname}")

    # Try to tag and terminate nodes.
    if nodes_to_terminate:
        print_node_list(nodes_to_terminate, "Nodes to Terminate")
        click.echo("Tagging and Terminating: "+str(NodeSet(','.join([node.hostname for node in nodes_to_terminate]))))
        for node in nodes_to_terminate:
            if node.slurm_state=="drain" or node.slurm_state=="down":
                run_tag(node)
                run_terminate(node)
            else:
                click.echo(f"Node is not drained, cannot terminate {node.hostname}")

    # Reset GPUs on nodes.
    if nodes_to_reset_GPUs:
        print_node_list(nodes_to_reset_GPUs, "Nodes to Reset the GPUs")
        click.echo("Resetting the GPUs on : "+str(NodeSet(','.join([node.hostname for node in nodes_to_reset_GPUs]))))
        for node in nodes_to_reset_GPUs:
            if node.slurm_state=="drain" or node.slurm_state=="down":
                run_reset_gpus(node)
            else:
                click.echo(f"Node is not drained, cannot reset GPUs on {node.hostname}")

    # Relaunch configuration step.
    if unconfigured_nodes:
        click.echo("Reconfiguring: "+str(NodeSet(','.join([node.hostname for node in unconfigured_nodes]))))
        run_configure(unconfigured_nodes)
        
    available_nodes=scan_host_api_logic()
    for shape in available_nodes.keys():
        click.echo(f"There are {available_nodes[shape]} available nodes of shape {shape} in your pool.")

