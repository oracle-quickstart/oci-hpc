#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os
sys.dont_write_bytecode = True
import logging

import click

from lib.cli import subcommands


@click.group()
def cli():
    """CLI for managing your application."""
    pass

if __name__ == "__main__":
    debug_level=logging.INFO
    if "MGMT_DEBUG" in os.environ.keys():
        if os.environ["MGMT_DEBUG"] != 0 and os.environ["MGMT_DEBUG"].lower() != "false":
            debug_level=logging.DEBUG
    logging.basicConfig(
        level=debug_level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.getLogger("oci").setLevel(logging.WARNING)

    for subcommand in subcommands:
        cli.add_command(subcommand)
    cli()
