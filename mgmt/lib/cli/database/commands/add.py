from typing_extensions import Required
import click
from lib.database import db_create_node

@click.command()
@click.argument('identifiers')
@click.option('--ip', help='IP Address of the node.', required=True)
@click.option('--cluster_name', help='Cluster name of the node.', required=True)
@click.option('--hostname', help='Hostname of the node.', required=True)
@click.option('--ocid', help='OCID of the node.', required=True)

def add(identifier, ip, cluster_name, hostname, ocid):
    """List all fabrics for nodes."""
    content={'ip_address': ip, 'cluster_name': cluster_name, 'status': 'starting', 'hostname': hostname, 'controller_status': 'configuring'}
    db_create_node(ocid, **content)