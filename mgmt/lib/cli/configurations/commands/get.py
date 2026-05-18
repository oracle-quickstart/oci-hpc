
import click
from lib.cli import completion
from lib.cli.configurations.display import print_config_info
from lib.database import get_config_by_name

@click.command()
@click.option('--name', required=True, help='Get configuration name.', shell_complete=completion.complete_configurations_all)
def get(name):
    """Get information about the configuration."""

    configuration = get_config_by_name(name)
    
    if not configuration:
        click.echo("Configuration not found.")
        return
    else: 
        print_config_info(configuration)
        
