"""
Implement the 'nodes list' subcommand.

This command allows nodes to be displayed in a variety of formats/styles.
"""

import click

import lib.database as db
from lib.cli.nodes import display
from lib.logger import logger

def callback_fields(ctx, param, value):
    """Process the fields spec for the --fields argument"""

    # ctx and param aren't used
    # pylint: disable=unused-argument

    try:
        return display.parse_fields_spec(value)
    except display.ListValidFields as exc:
        click.echo(str(exc))
        raise SystemExit(0) from exc
    except display.InvalidField as exc:
        raise click.BadParameter(str(exc)) from exc

# oops, redefined "format", and "filter"
# pylint: disable=redefined-builtin


@click.command("list")
@click.option(
    "--one-line",
    is_flag=True,
    help="Share the hostnames list in one line (or compact output with --json)"
)
@click.option(
    "--cluster",
    help="List nodes that are part of named cluster.")
@click.option(
    "--memory-cluster",
    help="List nodes that are part of named memory cluster."
)
@click.option(
    "--style",
    type=click.Choice(["lines", "box", "none"]),
    default="box", show_default=True,
    help="Table style for tabular output."
)
@click.option(
    "--format",
    type=click.Choice(["tabular", "node", "csv", "json"]),
    default="tabular", show_default=True,
    help="Output format"
)
@click.option(
    "--width",
    type=int,
    help="Width of output. [default: detect from terminal or COLUMNS env var]"
)
@click.option(
    "--columns",
    callback=callback_fields,
    help="""
        Comma separated list of fields to display. Also accepts ALL, DEFAULT,
        SIMPLE (all single-line fields), HC (all healthcheck fields + simple fields), or LIST (to list field names and exit)
    """
)
@click.option(
    "--no-header",
    is_flag=True,
    help="Do not include header in tabular/csv formats."
)
@click.option(
    '--fields',
    required=False,
    help='Add a list of fields to filter, Example: role=compute,status=running'
)
@click.option(
    "--terminated",
    is_flag=True,
    help="List terminated nodes instead of active nodes."
)
@click.option(
    "--terminated_delay",
    type=int,
    help="List terminated nodes instead in the last X minutes."
)
def list_cmd(columns, format, **options):
    """List nodes with various filters and formats
    Example:

  # List all nodes in a cluster\n
  mgmt nodes list --cluster mycluster

  # Lists all node hostnames in a boxed table format without headers, using a fixed width of 30\n
  mgmt nodes list --columns hostname --style box --no-header --width 30 
  
  # Lists all compute nodes in a json format with all fields\n
  mgmt nodes list --format json --columns all --fields role=compute
  """

    field_dict = {}
    if not options["fields"] is None:
        for field in options["fields"].split(','):
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
    if options["cluster"] is not None:
        field_dict["cluster_name"] = options["cluster"]

    if options["memory_cluster"] is not None:
        field_dict["memory_cluster_name"] = options["memory_cluster"]

    if options.get("terminated"):
        logger.debug("Using terminated nodes query")
        base_query = db.get_terminated_nodes_with_latest_healthchecks(delay=options.get("terminated_delay"))
    else:
        base_query = db.get_nodes_with_latest_healthchecks()

    query = db.get_query_by_fields(base_query,field_dict)
    nodes = query.all()
    if not nodes:
        click.echo("No nodes found.", err=True)

    display.display_nodes(
        nodes, format, columns,
        table_style=options["style"],
        one_line=options["one_line"],
        show_header=not options["no_header"],
        width=options["width"],
    )
