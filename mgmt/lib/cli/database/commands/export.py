
import click
from lib.database import db_create
from lib.logger import logger

@click.command()
@click.option(
    "--filename", default="export.sqlite", show_default=True,
    help="SQLite filename. Must not already exist."
)
@click.option(
    "--use-base", default=False, is_flag=True, show_default=True,
    help="""
        Use embedded Base metadata when creating target db. This can be used as
        very simple validation; if the source database schema doesn't match, an
        error may be raised.
    """
)
def export(filename, use_base):
    """Export database contents to a SQLite DB file. May not work if Python was
    built without sqlite support.
    """

    if pathlib.Path(filename).exists():
        raise click.BadParameter(f"{filename!r} already exists")

    logger.info(f"Exporting DB to {filename!r}")
    lib.database.db_export(outfile = filename)