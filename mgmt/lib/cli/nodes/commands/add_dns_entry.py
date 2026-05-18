import click
from ClusterShell.NodeSet import NodeSet

import lib.database as db
from lib.functions import get_ansiblevars
from lib.ociwrap import update_dns


@click.command("add-dns-entry")
@click.option(
    "--alternate_hostname",
    required=False,
    help="Alternate hostname to use for the DNS A record.",
)
@click.option(
    "--nodes",
    required=True,
    help="Comma separated list of nodes (IP, hostname, OCID, serial, or OCI name).",
)
def add_dns_entry(alternate_hostname, nodes):
    """Add or update DNS A record for a single node."""
    nodes_list = db.get_nodes_by_any(NodeSet(nodes))

    if not nodes_list:
        click.echo("Node not found.")
        return

    if len(nodes_list) > 1:
        raise click.ClickException("Please pass exactly one node to add-dns-entry.")

    node = nodes_list[0]
    inventory_path = f"/config/playbooks/inventory_{node.cluster_name}"
    ansiblevars = get_ansiblevars(
        f"/config/playbooks/inventory_{node.cluster_name}",
        ["zone_name", "vcn_compartment"]
    )
    hostname = alternate_hostname or node.hostname
    update_dns(
        node.ocid,
        ansiblevars["zone_name"],
        node.compartment_id,
        True,
        hostname,
        ansiblevars["vcn_compartment"],
        instance_ip=node.ip_address,
        hostname_convention=None
    )

    click.echo(f"Updated DNS entry: {hostname}.{ansiblevars['zone_name']}")