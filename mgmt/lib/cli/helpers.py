"""Utility functions to offload shared behavior.
"""
from functools import wraps

import click
from lib.cli import completion
import lib.database as db

from ClusterShell.NodeSet import NodeSet


def _filter_nodes_impl(nodes, fields, topology_filters=None):
    topology_filters = {
        field: value
        for field, value in (topology_filters or {}).items()
        if value
    }
    selector_count = int(bool(nodes)) + int(bool(fields)) + len(topology_filters)
    if selector_count != 1:
        ctx = click.get_current_context()
        click.echo("Error: You must specify exactly one node selector")
        click.echo()
        click.echo(ctx.get_help())
        ctx.exit(1)

    # If fields are provided, use them to filter nodes
    if fields:
        field_dict = {}
        for field in fields.split(","):
            if "=" not in field:
                raise click.BadParameter(f"Field must be in key=value format: {field}")
            key, value = field.split("=", 1)
            field_dict[key] = (
                value.lower() == "true" if value.lower() in ["true", "false"] else value
            )
        nodes_list = db.get_nodes_by_fields(field_dict)
    elif topology_filters:
        nodes_list = db.get_nodes_by_fields(topology_filters)
    else:
        # Use the provided node identifiers
        nodes_list = db.get_nodes_by_any(NodeSet(nodes)) if nodes else []

    return nodes_list


def click_filter_nodes(command=None, *, local_block=False):
    """Decorator to filter nodes either by node names or fields.

    Accepts SLURM notation for node names.

    If `local_block` is enabled, allow filtering by compute local block id, and pass it
    through as an argument to the consuming function.
    """
    def decorator(command):
        @click.option(
            "--nodes",
            required=False,
            help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)",
            shell_complete=completion.complete_node_identifiers,
        )
        @click.option(
            "--fields",
            required=False,
            help="Fields to filter nodes (e.g., role=compute,status=running)",
            shell_complete=completion.complete_node_fields,
        )
        @wraps(command)
        def wrapper(*args, nodes, fields, **kwargs):
            filtered_nodes = _filter_nodes_impl(
                nodes, fields, topology_filters={"rail_id": kwargs.get("compute_local_block_id")}
            )
            if not filtered_nodes:
                ctx = click.get_current_context()
                click.echo("No matching nodes found.")
                ctx.exit(1)
            return command(
                *args,
                nodes=filtered_nodes,
                **kwargs,
            )

        if local_block:
            wrapper = click.option(
                "--compute-local-block-id",
                "--local-block-id",
                "--local-block",
                "--localblock",
                "compute_local_block_id",
                required=False,
                help="Filter all nodes in this compute local block.",
            )(wrapper)

        return wrapper
    return decorator(command) if command else decorator
