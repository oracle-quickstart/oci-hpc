#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os
sys.dont_write_bytecode = True
import logging

import click

from lib.cli import subcommands


@click.group()
@click.option(
    "--debug",
    envvar="MGMT_DEBUG",
    is_flag=True,
    help="Enable debug log output. Can also be activated via MGMT_DEBUG in the environment",
)
def cli(debug):
    """CLI for managing your cluster."""
    log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.getLogger("oci").setLevel(logging.WARNING)


if __name__ == "__main__":
    for subcommand in subcommands:
        cli.add_command(subcommand)
    cli()
