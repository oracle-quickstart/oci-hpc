import click
from lib.cli.configurations.display import print_config_list_yaml_json,print_config_list
from lib.database import get_config_by_shape_and_partition, get_config_by_shape, get_config_by_partition, get_all_configs
from lib.logger import logger
from ClusterShell.NodeSet import NodeSet

@click.command()
@click.option(
    "--format",
    type=click.Choice(["tabular", "json","yaml"]),
    default="tabular", show_default=True,
    help="Output format"
)
@click.option('--output_file', help='Name of the output file.')
@click.option('--partition', help='Get all configurations in that defined partition.')
@click.option('--role', type=click.Choice(["compute", "login", "all"]), help='Get all configurations for compute or login.', default="all", show_default=True)
@click.option('--shape',  help='Get all configurations with a particular shape.')
def list(format, output_file, partition, role, shape):
    """List Configuration based on role, partition, or shape."""
    if partition:
        if shape:
            configurations = get_config_by_shape_and_partition(shape,partition, role)
            title=f"Shape={shape},Partition={partition},Role={role}"
        else:
            configurations = get_config_by_partition(partition, role)
            title=f"Partition={partition},Role={role}"
    else:
        if shape:
            configurations = get_config_by_shape(shape, role)
            title=f"Shape={shape},Role={role}"
        else:
            configurations = get_all_configs(role)
            title=f"Role={role}"
    if format=="yaml":
        print_config_list_yaml_json(configurations,output_file,type="yaml")
    elif format=="json":
        print_config_list_yaml_json(configurations,output_file,type="json")
    else:
        print_config_list(configurations,title)