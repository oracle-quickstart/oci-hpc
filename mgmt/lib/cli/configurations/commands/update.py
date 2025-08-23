import click
from lib.database import db_update_configuration


@click.command()
@click.option('--name', required=True, help='Share the hostnames list in one line')
@click.option(
    '--fields',
    required=True,
    help='Add a list of update to do, Example shape="VM.Standard.E5.Flex,instance_pool_ocpus=4"'
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
