import click
import lib.database as db
from lib.cli.status.display import render_status

def load_nodes():

    #  Load node details
    base_query = db.get_nodes_with_latest_healthchecks()
    field_dict = {}
    query = db.get_query_by_fields(base_query,field_dict)
    nodes = query.all()
    keys = None
    nodes = [db.node_to_dict(node, keys) for node in nodes]
    return nodes

###
# click options and command details
###

@click.command("status")
@click.option(
    "--no_color",
    is_flag=True,
    default=False,
    required=False,
    help="Disable color output."
)
###
# Main 'status' command
###
def cmd(no_color):
    """
    Display an overview status of the OCI-HPC Stack

    By default the command runs once and prints the status in color.
    """
    
    nodes = load_nodes()
    status = render_status(nodes, no_color)
    click.echo(status)
    return

