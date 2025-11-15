from typing_extensions import Required
import click
from lib.database import db_create_node, get_nodes_by_id
from lib.functions import get_nodes_ocid_by_subnet, get_ansiblevars
from lib.logger import logger
from lib.ociwrap import update_dns, update_display_name

import configparser
import ipaddress

def is_valid_cidr(cidr):
    try:
        ipaddress.ip_network(cidr, strict=False)  # strict=False lets /32 and host IPs pass
        return True
    except ValueError:
        return False

http_port=9876
@click.command()
@click.argument('cidr')
@click.option(
    "--dns", default=False, is_flag=True, show_default=True,
    help="Scan DNS"
)
@click.option(
    "--change_hostname", default=False, is_flag=True, show_default=True,
    help="Change OCI hostname"
)
def scan_vcn(cidr, dns, change_hostname):
    """Scan the specified VCN CIDR to list nodes"""
    if not is_valid_cidr(cidr):
        logger.error(f"Invalid CIDR: {cidr}")
        exit()
    logger.debug(f"Scanning subnet: {cidr}")
    content_dict=get_nodes_ocid_by_subnet(cidr,http_port)

    nodes = get_nodes_by_id(content_dict.values())
    logger.debug(f"Found {len(nodes)} nodes in the subnet")
    logger.debug(f"Nodes: {nodes}")
    for ip in content_dict.keys():
        node_found=False
        for node in nodes:
            if node.ocid == content_dict[ip]["ocid"]:
                node_found=True
                logger.debug(f"Node {node.hostname} already exists")
                continue
        if not node_found:
            logger.debug(f"Node {ip} not found in the database")
            content={'ip_address': ip, 'status': 'starting', 'controller_status': 'configuring'}
            db_create_node(content_dict[ip]["ocid"], **content)
            logger.debug(f"Node {ip} created")
        if dns:
            ansiblevars=get_ansiblevars("/config/playbooks/inventory_"+content_dict[ip]["cluster_name"],["zone_name"])
            zone_name=ansiblevars["zone_name"]
            update_dns(content_dict[ip]["ocid"], zone_name, content_dict[ip]["compartment_id"], True, content_dict[ip]["hostname"])
        if change_hostname:
            update_display_name(content_dict[ip]["ocid"], content_dict[ip]["hostname"])