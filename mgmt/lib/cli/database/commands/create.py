
import click
from lib.database import db_create
from lib.logger import logger

@click.command()
def create():
    """Create database/tables. Will not recreate tables that already exist."""
    logger.info(f"Initializing DB")
    db_create()

