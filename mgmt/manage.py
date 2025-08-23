#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
sys.dont_write_bytecode = True
import logging

import click

from lib.cli import subcommands


@click.group()
def cli():
    """CLI for managing your application."""
    pass

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.getLogger("oci").setLevel(logging.WARNING)

    for subcommand in subcommands:
        cli.add_command(subcommand)
    cli()
