import click
from lib.cli import completion
from lib.database import db_duplicate_configuration, db_import_configuration, get_controller_node
from lib.functions import run_ansible_slurm_reconcile
from lib.logger import logger


def reconcile_slurm_configuration():
    controller = get_controller_node()
    if controller is None or not controller.hostname:
        logger.info("Skipping Slurm reconcile because the controller is not registered in the mgmt database yet")
        return
    controller_hostname = controller.hostname

    logger.info("Triggering Slurm reconcile on controller %s", controller_hostname)
    if not run_ansible_slurm_reconcile(controller_hostname):
        raise click.ClickException(
            "Configuration was updated in the database, but Slurm reconcile failed."
        )

@click.group()
def create():
    """Create Configuration."""
    pass

@create.command()       
@click.option('--configuration', required=True, help='Name of the existing configuration to copy.', shell_complete=completion.complete_configurations_all)
@click.option('--name', required=True, help='Name for the new configuration.')
def from_existing(configuration,name):
    """Duplicate Configuration with new name."""
    success = db_duplicate_configuration(configuration, name)
    if not success:
        click.echo(f"Could not duplicate the configuration with name {configuration}.")
        return
    reconcile_slurm_configuration()
    logger.info("Configuration %s has been created and Slurm reconcile was triggered", name)
@create.command()       
@click.option('--file', required=True, help='Name of the json or yaml file.')
def from_file(file):
    """Create Configurations from file."""
    success = db_import_configuration(file)
    if not success:
        click.echo(f"Could not duplicate the configuration from file {file}.")
        return
    reconcile_slurm_configuration()
    logger.info("Configuration from file %s has been imported and Slurm reconcile was triggered", file)
