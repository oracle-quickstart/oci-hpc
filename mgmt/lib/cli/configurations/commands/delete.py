import click
from lib.cli import completion
from lib.database import db_delete_configuration, get_controller_node
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

@click.command()
@click.option('--configuration', required=True, help='Name of the configuration to delete.', shell_complete=completion.complete_configurations_all)
def delete(configuration):
    """Delete Configuration."""
    success =  db_delete_configuration(configuration)
    if not success:
        click.echo(f"Could not delete the configuration with name {configuration}.")
        return
    reconcile_slurm_configuration()
    logger.info("Configuration %s has been deleted and Slurm reconcile was triggered", configuration)
