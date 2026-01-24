import click
from lib.database import db_delete_configuration
from lib.logger import logger

@click.command()
@click.option('--configuration', required=True, help='Name of the configuration to delete.')
def delete(configuration):
    """Delete Configuration."""
    success =  db_delete_configuration(configuration)
    if not success:
        click.echo(f"Could not delete the configuration with name {configuration}.")
        return
    logger.warning(f"Configuration {configuration} has been deleted. Consider updating Slurm with 'mgmt configurations update-slurm' to sync slurmctld and the database")