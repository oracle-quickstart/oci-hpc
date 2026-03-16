import click
from lib.database import get_nodes_by_any, db_update_node

from ClusterShell.NodeSet import NodeSet

@click.command()
@click.argument('identifiers')
@click.option(
    '--fields',
    required=True,
    help='Add a list of update to do, Example shape=VM.Standard.E5.Flex,instance_pool_ocpus=4'
)

def update(identifiers, fields):
    """Update a field for a list of nodes."""
    nodes = get_nodes_by_any(NodeSet(identifiers))
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

    for node in nodes:
        db_update_node(node, **field_dict)