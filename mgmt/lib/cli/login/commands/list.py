import click
from lib.database import get_all_login_nodes
from lib.logger import logger
import json
@click.group()
def list():
    """List commands for nodes."""
    pass  
@click.option(
    "--format",
    type=click.Choice(["tabular", "json"]),
    default="tabular", show_default=True,
    help="Output format"
)
@list.command()
def list(format):
    """List all login nodes."""
    logins = get_all_login_nodes()
    logins_string=", ".join([login.hostname for login in logins])
    
    if format=="json":
        print(json.dumps([login.hostname for login in logins], indent=4))
    else:
        click.echo(f"Logins Available: {logins_string}")

        