from typing_extensions import Required
import click
from lib.database import db_create_node, get_nodes_by_id
from lib.functions import get_nodes_ocid_by_subnet
from lib.logger import logger

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
def scan_vcn(cidr):
    """Scan the specified VCN CIDR to list nodes"""
    if not is_valid_cidr(cidr):
        logger.error(f"Invalid CIDR: {cidr}")
        exit()
    logger.debug(f"Scanning subnet: {cidr}")
    ocid_dict=get_nodes_ocid_by_subnet(cidr,http_port)

    nodes = get_nodes_by_id(ocid_dict.values())
    logger.debug(f"Found {len(nodes)} nodes in the subnet")
    logger.debug(f"Nodes: {nodes}")
    for ip in ocid_dict.keys():
        node_found=False
        for node in nodes:
            if node.ocid == ocid_dict[ip]:
                node_found=True
                logger.debug(f"Node {node.hostname} already exists")
                continue
        if not node_found:
            logger.debug(f"Node {ip} not found in the database")
            content={'ip_address': ip, 'status': 'starting', 'controller_status': 'configuring'}
            db_create_node(ocid_dict[ip], **content)
            logger.debug(f"Node {ip} created")