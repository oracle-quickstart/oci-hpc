import click
from lib.database import db_update_configuration
from lib.logger import logger

@click.command()
@click.option('--name', required=True, help='Name of the configuration to update')
@click.option(
    '--fields',
    required=True,
    help='Comma-separated list of updates to apply, Example: shape="VM.Standard.E5.Flex,instance_pool_ocpus=4"'
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
    logger.warning(f"Configuration {name} has been updated. Consider updating Slurm with 'mgmt configurations update-slurm' to sync slurmctld and the database")
