"""
Implement the 'nodes list' subcommand.

This command allows nodes to be displayed in a variety of formats/styles.
"""

import click

import lib.database as db
from lib.cli.nodes import display


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
    "--filter",
    type=click.Choice(
        ["all", "compute", "controller", "management", "terminated"]
    ),
    default="all", show_default=True,
    help="Select what type of nodes are displayed."
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
    "--fields",
    callback=callback_fields,
    help="""
        Comma separated list of fields to display. Also accepts ALL, DEFAULT,
        SIMPLE (all single-line fields), or LIST (to list field names and exit)
    """
)
@click.option(
    "--no-header",
    is_flag=True,
    help="Do not include header in tabular/csv formats."
)
def list_cmd(fields, filter, format, **options):
    """List nodes with various filters and formats"""

    with db.DBConn() as session:
        query = db.filter_nodes(session, filter=filter)
        query = db.filter_nodes_by_cluster(
            query,
            cluster_name=options["cluster"],
            memory_cluster_name=options["memory_cluster"],
        )

        nodes = query.all()

    if not nodes:
        click.echo("No nodes found.")
        return

    display.display_nodes(
        nodes, format, fields,
        table_style=options["style"],
        one_line=options["one_line"],
        show_header=not options["no_header"],
        width=options["width"],
    )
