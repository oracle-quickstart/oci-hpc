import click
import lib.database as db
from lib.cli.status.display import render_status
from lib.cli.status.health import render_health


def load_nodes():

    #  Load node details
    base_query = db.get_nodes_with_latest_healthchecks()
    field_dict = {}
    query = db.get_query_by_fields(base_query,field_dict)
    try:
        nodes = query.all()
        keys = None
        nodes = [db.node_to_dict(node, keys) for node in nodes]
        return nodes
    finally:
        query.session.close()

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
@click.pass_context
def cmd(ctx, no_color):
    """
    Display an overview status of the OCI-HPC Stack

    Shows the control plane health first (services, mounts and automation
    required for the cluster to accept jobs), then the node-centric cluster
    status. Exits non-zero when a control plane check fails or when more
    than half of the nodes need attention.
    """

    healthy = render_health(no_color)

    nodes = load_nodes()
    nodes_healthy = render_status(nodes, no_color)

    ctx.exit(0 if healthy and nodes_healthy else 1)
