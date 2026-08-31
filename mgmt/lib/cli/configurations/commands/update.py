import click
from lib.cli import completion
from lib.database import db_update_configuration, get_controller_node
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
@click.option('--name', required=True, help='Name of the configuration to update', shell_complete=completion.complete_configurations_all)
@click.option(
    '--fields',
    required=True,
    help='Comma-separated list of updates to apply, Example: shape="VM.Standard.E5.Flex,instance_pool_ocpus=4"',
    shell_complete=completion.complete_configuration_fields,
)
def update(name, fields):
    """Update Configuration"""
    field_dict = {}

    for field in fields.split(','):
        if '=' not in field:
            raise click.BadParameter(f"Field must be in key=value format: {field}")

        key, value = field.split('=', 1)

        if value.lower() == "true":
            new_value = True
        elif value.lower() == "false":
            new_value = False
        else:
            new_value = value

        field_dict[key] = new_value

    db_update_configuration(name, **field_dict)
    reconcile_slurm_configuration()
    logger.info("Configuration %s has been updated and Slurm reconcile was triggered", name)
