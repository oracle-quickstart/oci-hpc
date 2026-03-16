
import click
from lib.cli.configurations.display import print_config_info
from lib.database import get_config_by_name
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

@click.command()
@click.option('--name', required=True, help='Get configuration name.')
def get(name):
    """Get information about the configuration."""

    configuration = get_config_by_name(name)
    
    if not configuration:
        click.echo("Configuration not found.")
        return
    else: 
        print_config_info(configuration)
        