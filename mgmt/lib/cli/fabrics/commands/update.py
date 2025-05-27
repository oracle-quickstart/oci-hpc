import click
from lib.cli.nodes.display import print_node_list
from lib.database import get_all_nodes, db_update_configuration
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

@click.command()
@click.option('--name', required=True, help='Share the hostnames list in one line')
@click.option('--fields', required=True, help='Add a list of update to do, Example shape="VM.Standard.E5.Flex,instance_pool_ocpus=4"') 
def update(name,fields):
    """Update Configuration"""
    field_dict = {}
    for f in fields.split(','):
        if '=' not in f:
            raise click.BadParameter(f"Field must be in key=value format: {f}")
        key, value = f.split('=', 1)
        if value.lower()=="true":
            new_value=True
        elif value.lower()=="false":
            new_value=False
        else:
            new_value=value
        field_dict[key] = new_value
    db_update_configuration(name, **field_dict)