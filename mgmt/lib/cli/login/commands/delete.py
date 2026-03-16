
import click
from lib.logger import logger
from lib.ociwrap import run_terminate
import lib.database as db

### 
### Delete a login node
###

@click.command()
@click.option('--hostname', required=True, help='Specify the name of the login node')
def delete(hostname):
    """Delete a login node."""
    field_dict = {"hostname": hostname, "role":"login"}
    nodes_list = db.get_query_by_fields(db.get_nodes_with_latest_healthchecks(),field_dict).all()
    if nodes_list is None:
        click.echo(f"Login node {hostname} not found.")
        return
    for node in nodes_list:
        run_terminate(node)