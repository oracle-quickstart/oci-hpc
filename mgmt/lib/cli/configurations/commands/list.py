import click
from lib.cli.configurations.display import print_config_list_yaml_json,print_config_list
from lib.database import get_config_by_shape_and_partition, get_config_by_shape, get_config_by_partition, get_all_configs
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

@click.command()
@click.option('--yaml', is_flag=True, show_default=True, default=False, help='List in YAML format.')
@click.option('--json', is_flag=True, show_default=True, default=False, help='List in JSON format.')
@click.option('--output_file', help='Name of the output file.')
@click.option('--partition', help='Get all configurations in that defined partition.')
@click.option('--shape',  help='Get all configurations with a particular shape.')
def list(yaml, json, output_file, partition, shape):
    """List commands for nodes."""
    if partition:
        if shape:
            configurations = get_config_by_shape_and_partition(shape,partition)
            title=f"Shape={shape},Partition={partition}"
        else:
            configurations = get_config_by_partition(partition)
            title=f"Partition={partition}"
    else:
        if shape:
            configurations = get_config_by_shape(shape)
            title=f"Shape={shape}"
        else:
            configurations = get_all_configs()
            title="All"
    if yaml:
        print_config_list_yaml_json(configurations,output_file, type="yaml")
    elif json:
        print_config_list_yaml_json(configurations,output_file, type="json")
    else:
        print_config_list(configurations,title)