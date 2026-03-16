import click
from lib.database import db_duplicate_configuration, db_import_configuration
from lib.logger import logger

@click.group()
def create():
    """Create Configuration."""
    pass

@create.command()       
@click.option('--configuration', required=True, help='Name of the existing configuration to copy.')
@click.option('--name', required=True, help='Name for the new configuration.')
def from_existing(configuration,name):
    """Duplicate Configuration with new name."""
    success = db_duplicate_configuration(configuration, name)
    if not success:
        click.echo(f"Could not duplicate the configuration with name {configuration}.")
        return
    logger.warning(f"Configuration {name} has been created. Consider updating Slurm with 'mgmt configurations update-slurm' to sync slurmctld and the database")
@create.command()       
@click.option('--file', required=True, help='Name of the json or yaml file.')
def from_file(file):
    """Create Configurations from file."""
    success = db_import_configuration(file)
    if not success:
        click.echo(f"Could not duplicate the configuration from file {file}.")
        return
    logger.warning(f"Configuration has been created from file {file}. Consider updating Slurm with 'mgmt configurations update-slurm' to sync slurmctld and the database")