import click
from lib.database import db_create_node, get_nodes_by_id, get_all_nodes, db_update_node
from lib.functions import get_nodes_ocid_by_subnet, get_ansiblevars, update_hosts_on_cluster
from lib.logger import logger
from lib.ociwrap import update_dns, update_display_name

import ipaddress

def is_valid_cidr(cidr):
    try:
        ipaddress.ip_network(cidr, strict=False)  # strict=False lets /32 and host IPs pass
        return True
    except ValueError:
        return False

http_port=9876


def scan_vcn_logic(cidr, dns=False, change_hostname=False, manage_hosts=None, cfg=None, prune_missing=False):
    """Core logic to scan VCN CIDR and optionally update /etc/hosts."""
    if not is_valid_cidr(cidr):
        logger.error(f"Invalid CIDR: {cidr}")
        return False
    logger.info(f"Scanning subnet {cidr} for nodes")
    content_dict = get_nodes_ocid_by_subnet(cidr, http_port)

    ocid_list = [entry.get("ocid") for entry in content_dict.values() if isinstance(entry, dict) and entry.get("ocid")]
    nodes = get_nodes_by_id(ocid_list)
    logger.info(f"Discovered {len(content_dict)} IPs responding, {len(nodes)} already in DB")
    created = 0
    responder_ips = set(content_dict.keys())
    network = ipaddress.ip_network(cidr, strict=False)

    for ip in content_dict.keys():
        node_found = False
        for node in nodes:
            if node.ocid == content_dict[ip]["ocid"]:
                node_found = True
                logger.debug(f"Node {node.hostname} already exists")
                continue
        if not node_found:
            logger.debug(f"Node {ip} not found in the database")
            content = {'ip_address': ip, 'status': 'starting', 'controller_status': 'configuring'}
            db_create_node(content_dict[ip]["ocid"], **content)
            logger.debug(f"Node {ip} created")
            created += 1
        if dns:
            ansiblevars = get_ansiblevars(
                f"/config/playbooks/inventory_{content_dict[ip]['cluster_name']}",
                ["zone_name", "vcn_compartment"]
            )
            update_dns(
                content_dict[ip]["ocid"],
                ansiblevars["zone_name"],
                content_dict[ip]["compartment_id"],
                True,
                content_dict[ip]["hostname"],
                ansiblevars["vcn_compartment"],
                instance_ip=ip
            )
        if change_hostname:
            update_display_name(content_dict[ip]["ocid"], content_dict[ip]["hostname"])

    if prune_missing:
        # Prune nodes in this CIDR that did not respond: mark unreachable to drop from /etc/hosts
        nodes_in_cidr = [n for n in get_all_nodes() if n.ip_address and ipaddress.ip_address(n.ip_address) in network]
        pruned = 0
        for n in nodes_in_cidr:
            if n.ip_address not in responder_ips:
                if n.status != "unreachable":
                    db_update_node(n, status="unreachable")
                    pruned += 1

        if pruned:
            logger.info(f"Marked {pruned} nodes unreachable (no response in scan {cidr})")

    cfg_dict = cfg or {}
    manage_flag = cfg_dict.get("manage_hosts") if manage_hosts is None else manage_hosts
    # Default prune_missing to manage_flag when not explicitly set
    prune_flag = prune_missing if prune_missing is not None else manage_flag
    clush_parallel = cfg_dict.get("clush_parallel_executions", 10)
    logger.info(f"Scan {cidr}: created {created} new nodes, updated {len(nodes)} existing")
    if manage_flag:
        logger.info("Updating /etc/hosts across cluster after VCN scan")
        update_hosts_on_cluster(manage_hosts=manage_flag, clush_parallel_executions=clush_parallel)
    return True


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
@click.option(
    "--manage-hosts/--no-manage-hosts",
    default=None,
    show_default=False,
    help="Update /etc/hosts across discovered nodes (overrides config)."
)
@click.option(
    "--prune-missing/--no-prune-missing",
    default=False,
    show_default=True,
    help="Mark nodes in CIDR that did not respond as unreachable."
)
@click.pass_obj
def scan_vcn(cfg, cidr, dns, change_hostname, manage_hosts, prune_missing):
    """Scan the specified VCN CIDR to list nodes"""
    scan_vcn_logic(cidr, dns=dns, change_hostname=change_hostname, manage_hosts=manage_hosts, cfg=cfg, prune_missing=prune_missing)
