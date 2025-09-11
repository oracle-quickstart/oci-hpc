import click
from lib.database import get_clusters
from lib.logger import logger
import json
@click.group()
def list():
    """List commands for nodes."""
    pass  
@click.option(
    "--format",
    type=click.Choice(["tabular", "json"]),
    default="tabular", show_default=True,
    help="Output format"
)
@list.command()
def list(format):
    clusters = get_clusters()
    cluster_string=", ".join(clusters)
    
    if format=="json":
        print(json.dumps(clusters, indent=4))
    else:
        click.echo(f"Clusters Available: {cluster_string}")

        