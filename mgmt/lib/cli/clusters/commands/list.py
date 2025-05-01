import click
from lib.database import get_clusters
from lib.logger import logger

@click.group()
def list():
    """List commands for nodes."""
    pass  
@list.command()
def list():
    clusters = get_clusters()
    cluster_string=", ".join(clusters)
    click.echo(f"Clusters Available: {cluster_string}")