#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, os
sys.dont_write_bytecode = True

import logging
import click
import configparser
from pathlib import Path

from lib.cli import subcommands


DEFAULTS = {
    "debug": False,
    "clush_parallel_executions": 10,
    "active_healthchecks": True,
    "active_healthchecks_frequency": 24,
    "multi_nodes_healthchecks": True,
    "multi_nodes_healthchecks_frequency": 24,
}

DEFAULT_CONFIG_PATHS = [
    "/config/mgmt/mgmt.ini",
    str(Path.home() / ".mgmt.ini"),
]


def load_config(path: str | None) -> dict:
    cfg = configparser.ConfigParser()

    # Load defaults first
    cfg.read_dict({"mgmt": {k: str(v) for k, v in DEFAULTS.items()}})

    # Then load from file(s)
    if path:
        cfg.read(path)
    else:
        cfg.read(DEFAULT_CONFIG_PATHS)

    section = "mgmt"

    # Typed reads (ConfigParser stores strings)
    return {
        "debug": cfg.getboolean(section, "debug"),
        "clush_parallel_executions": cfg.getint(section, "clush_parallel_executions"),
        "active_healthchecks": cfg.getboolean(section, "active_healthchecks"),
        "active_healthchecks_frequency": cfg.getint(section, "active_healthchecks_frequency"),
        "multi_nodes_healthchecks": cfg.getboolean(section, "multi_nodes_healthchecks"),
        "multi_nodes_healthchecks_frequency": cfg.getint(section, "multi_nodes_healthchecks_frequency"),
    }


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, exists=False),
    envvar="MGMT_CONFIG",
    help="Path to config file (INI). Can also be set via MGMT_CONFIG.",
)
@click.option(
    "--debug/--no-debug",
    default=None,  # None means "not set on CLI"
    envvar="MGMT_DEBUG",
    help="Enable debug log output (overrides config).",
)
@click.option(
    "--clush-parallel-executions",
    type=int,
    default=None,
    show_default=False,
    help="Number of parallel clush executions (overrides config).",
)
@click.option(
    "--active-healthchecks/--no-active-healthchecks",
    default=None,
    show_default=False,
    help="Enable/disable active healthchecks (overrides config).",
)
@click.option(
    "--active-healthchecks-frequency",
    type=int,
    default=None,
    show_default=False,
    help="Active healthchecks frequency in hours (overrides config).",
)
@click.option(
    "--multi-nodes-healthchecks/--no-multi-nodes-healthchecks",
    default=None,
    show_default=False,
    help="Enable/disable multi-node healthchecks (overrides config).",
)
@click.option(
    "--multi-nodes-healthchecks-frequency",
    type=int,
    default=None,
    show_default=False,
    help="Multi-node healthchecks frequency in hours (overrides config).",
)
@click.pass_context
def cli(ctx, config_path, debug,
        clush_parallel_executions,
        active_healthchecks, active_healthchecks_frequency,
        multi_nodes_healthchecks, multi_nodes_healthchecks_frequency):
    """CLI for managing your cluster."""

    # Load config (defaults -> config file)
    cfg = load_config(config_path)

    # Apply CLI overrides (only when option provided)
    if debug is not None:
        cfg["debug"] = debug
    if clush_parallel_executions is not None:
        cfg["clush_parallel_executions"] = clush_parallel_executions
    if active_healthchecks is not None:
        cfg["active_healthchecks"] = active_healthchecks
    if active_healthchecks_frequency is not None:
        cfg["active_healthchecks_frequency"] = active_healthchecks_frequency
    if multi_nodes_healthchecks is not None:
        cfg["multi_nodes_healthchecks"] = multi_nodes_healthchecks
    if multi_nodes_healthchecks_frequency is not None:
        cfg["multi_nodes_healthchecks_frequency"] = multi_nodes_healthchecks_frequency

    # Store final config for subcommands to use
    ctx.ensure_object(dict)
    ctx.obj = cfg

    # Logging based on final config
    log_level = logging.DEBUG if cfg["debug"] else logging.INFO
    logging.basicConfig(level=log_level, format="%(asctime)s - %(levelname)s - %(message)s")
    logging.getLogger("oci").setLevel(logging.WARNING)


if __name__ == "__main__":
    for subcommand in subcommands:
        cli.add_command(subcommand)
    cli(obj={})