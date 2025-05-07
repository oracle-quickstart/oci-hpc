import click
from lib.database import get_clusters
from lib.logger import logger
import json
@click.group()
def list():
    """List commands for nodes."""
    pass  
@click.option('--json','as_json', is_flag=True, help='Get full information about the node.', default=False)
@list.command()
def list(as_json):
    clusters = get_clusters()
    cluster_string=", ".join(clusters)
    
    if as_json:
        print(json.dumps(clusters, indent=4))
    else:
        click.echo(f"Clusters Available: {cluster_string}")

        