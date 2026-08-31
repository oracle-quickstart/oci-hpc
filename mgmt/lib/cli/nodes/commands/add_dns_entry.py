import click
import ipaddress
import pathlib
from ClusterShell.NodeSet import NodeSet

import lib.database as db
from lib.functions import get_ansiblevars
from lib.ociwrap import update_dns


DNS_ANSIBLEVARS = ["zone_name", "vcn_compartment"]


def _single_ip(value, option_name):
    parts = [part.strip() for part in str(value).split(",") if part.strip()]
    if len(parts) != 1:
        raise click.ClickException(f"Please pass exactly one IP address to {option_name}.")

    try:
        return str(ipaddress.IPv4Address(parts[0]))
    except ValueError:
        return None


def _inventory_candidates(cluster_name=None):
    candidates = []
    if cluster_name:
        candidates.append(f"/config/playbooks/inventory_{cluster_name}")

    controller = db.get_controller_node()
    if controller and controller.cluster_name:
        controller_inventory = f"/config/playbooks/inventory_{controller.cluster_name}"
        if controller_inventory not in candidates:
            candidates.append(controller_inventory)

    candidates.append("/config/playbooks/inventory")
    return candidates


def _get_dns_ansiblevars(cluster_name=None):
    errors = []
    for inventory_path in _inventory_candidates(cluster_name):
        if not pathlib.Path(inventory_path).exists():
            continue
        try:
            ansiblevars = get_ansiblevars(inventory_path, DNS_ANSIBLEVARS)
        except Exception as exc:
            errors.append(f"{inventory_path}: {exc}")
            continue

        if all(ansiblevars.get(var) for var in DNS_ANSIBLEVARS):
            return ansiblevars
        errors.append(f"{inventory_path}: missing zone_name or vcn_compartment")

    detail = "; ".join(errors) if errors else "no inventory files found"
    raise click.ClickException(f"Could not load DNS inventory variables: {detail}")


@click.command("add-dns-entry")
@click.option(
    "--alternate_hostname",
    required=False,
    help="Alternate hostname to use for the DNS A record.",
)
@click.option(
    "--nodes",
    required=False,
    help="Comma separated list of nodes (IP, hostname, OCID, serial, or OCI name).",
)
@click.option(
    "--ip",
    "ip_address",
    required=False,
    help="IP address to use for the DNS A record without requiring a node DB entry.",
)
def add_dns_entry(alternate_hostname, nodes, ip_address):
    """Add or update DNS A record for a single node or IP address."""
    if bool(nodes) == bool(ip_address):
        raise click.ClickException("Please pass exactly one of --nodes or --ip.")

    node = None
    direct_ip = None
    if ip_address:
        direct_ip = _single_ip(ip_address, "--ip")
        if direct_ip is None:
            raise click.ClickException(f"Invalid IP address: {ip_address}")
    else:
        try:
            direct_ip = _single_ip(nodes, "--nodes")
        except click.ClickException:
            direct_ip = None

        if direct_ip:
            nodes_list = db.get_nodes_by_any([direct_ip])
        else:
            nodes_list = db.get_nodes_by_any(NodeSet(nodes))

        if len(nodes_list) > 1:
            raise click.ClickException("Please pass exactly one node to add-dns-entry.")

        if nodes_list:
            node = nodes_list[0]
        else:
            if direct_ip is None:
                click.echo("Node not found.")
                return

    if node:
        if not node.ip_address:
            raise click.ClickException(
                f"Node {node.hostname} does not have an IP address in the database."
            )
        target_ip = node.ip_address
        hostname = alternate_hostname or node.hostname
        cluster_name = node.cluster_name
        instance_ocid = node.ocid
        compartment_id = node.compartment_id
    else:
        if not alternate_hostname:
            raise click.ClickException("--alternate_hostname is required when using an IP address.")
        target_ip = direct_ip
        hostname = alternate_hostname
        cluster_name = None
        instance_ocid = None
        compartment_id = None

    ansiblevars = _get_dns_ansiblevars(cluster_name)
    update_dns(
        instance_ocid,
        ansiblevars["zone_name"],
        compartment_id,
        True,
        hostname,
        ansiblevars["vcn_compartment"],
        instance_ip=target_ip,
        hostname_convention=None
    )

    click.echo(f"Updated DNS entry: {hostname}.{ansiblevars['zone_name']} -> {target_ip}")


@click.command("delete-dns-entry")
@click.option(
    "--hostname",
    required=True,
    help="Hostname to remove from the DNS A records.",
)
@click.option(
    "--cluster",
    "cluster_name",
    required=False,
    help="Cluster name used to select the inventory DNS variables.",
)
def delete_dns_entry(hostname, cluster_name):
    """Delete a DNS A record by hostname."""
    ansiblevars = _get_dns_ansiblevars(cluster_name)
    update_dns(
        None,
        ansiblevars["zone_name"],
        None,
        False,
        hostname,
        ansiblevars["vcn_compartment"],
    )

    click.echo(f"Deleted DNS entry: {hostname}.{ansiblevars['zone_name']}")
