import click
from lib.cli import completion
from lib.database import db_delete_configuration
from lib.logger import logger

@click.command()
@click.option('--configuration', required=True, help='Name of the configuration to delete.', shell_complete=completion.complete_configurations_all)
def delete(configuration):
    """Delete Configuration."""
    success =  db_delete_configuration(configuration)
    if not success:
        click.echo(f"Could not delete the configuration with name {configuration}.")
        return
    logger.warning(f"Configuration {configuration} has been deleted. Consider updating Slurm with 'mgmt configurations update-slurm' to sync slurmctld and the database")
