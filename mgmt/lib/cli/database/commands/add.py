from typing_extensions import Required
import click
from lib.database import db_create_node
from lib.functions import get_nodes_ocid_by_ip

http_port=9876
@click.command()
@click.option('--ip', help='IP Address of the node.', required=True)
@click.option('--hostname', help='Hostname of the node.', required=False)
@click.option('--ocid', help='OCID of the node.', required=False)

def add(ip, hostname, ocid):
    """Add specific node to the DB."""
    if ocid is None:
        ocid_dict=get_nodes_ocid_by_ip([ip],http_port)
        if ocid_dict[ip] is None:
            logger.error(f"Node with {ip} is not ready yet. The webserver containing the node info is not available")
            return
        ocid=ocid_dict[ip]["ocid"]
    content={'ip_address': ip, 'status': 'starting', 'controller_status': 'configuring'}
    if hostname is not None:
        content={'ip_address': ip, 'status': 'starting', 'hostname': hostname, 'controller_status': 'configuring'}
    db_create_node(ocid, **content)