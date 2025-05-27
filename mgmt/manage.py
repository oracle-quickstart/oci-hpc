#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.dont_write_bytecode = True

import click
from lib.cli.nodes import nodes
from lib.cli.network import network
from lib.cli.clusters import clusters
from lib.cli.configurations import configurations
from lib.cli.services import services
from lib.cli.recommendations import recommendations
from lib.cli.configurations import configurations
from lib.cli.fabrics import fabrics


@click.group()
def cli():
    """CLI for managing your application."""
    pass
        
if __name__ == "__main__":
    cli.add_command(nodes.nodes)
    cli.add_command(network.network)
    cli.add_command(clusters.clusters)
    cli.add_command(services.services)
    cli.add_command(recommendations.recommendations)
    cli.add_command(configurations.configurations)
    cli.add_command(fabrics.fabrics)
    cli()