import csv
import json
import os
import sys

import click
import rich

from ClusterShell.NodeSet import NodeSet

import lib.database as db

# Not wrong, but the messages are obscuring real errors
# pylint: disable=missing-function-docstring


def print_nodes_info(nodes, full=False):
    for node in nodes:
        table = rich.table.Table(show_header=False, show_lines=True)
        table.add_column(justify="left")
        table.add_column(justify="left")
        if not full:
            table.add_row("Hostname", node.hostname)
            table.add_row("status", node.status)
            table.add_row("Cluster", node.cluster_name)
            table.add_row("ID", str(node.ocid))
            table.add_row("Serial", node.serial)
            table.add_row("IP", node.ip_address)
            table.add_row("Shape", node.shape)
            table.add_row("passive_healthcheck_recommendation", node.passive_healthcheck_recommendation)
            table.add_row("active_healthcheck_recommendation", node.active_healthcheck_recommendation)
        else:
            table.add_row("ip_address", node.ip_address)
            table.add_row("controller_status", node.controller_status)
            table.add_row("started_time", node.started_time)
            table.add_row("status", node.status)
            table.add_row("availability_domain", node.availability_domain)
            table.add_row("first_time_reachable", node.first_time_reachable)
            table.add_row("cluster_name", node.cluster_name)
            table.add_row("compartment_id", node.compartment_id)
            table.add_row("tenancy_id", node.tenancy_id)
            table.add_row("compute_status", node.compute_status)
            table.add_row("controller_name", node.controller_name)
            table.add_row("fss_mount", node.fss_mount)
            table.add_row("gpu_memory_fabric", node.gpu_memory_fabric)
            table.add_row("hostname", node.hostname)
            table.add_row("hpc_island", node.hpc_island)
            table.add_row("image_id", node.image_id)
            table.add_row("instance_type", node.instance_type)
            table.add_row("last_time_reachable", node.last_time_reachable)
            table.add_row("network_block_id", node.network_block_id)
            table.add_row("memory_cluster_name", node.memory_cluster_name)
            table.add_row("oci_name", node.oci_name)
            table.add_row("ocid", node.ocid)
            table.add_row("rack_id", node.rack_id)
            table.add_row("rail_id", node.rail_id)
            table.add_row("role", node.role)
            table.add_row("serial", node.serial)
            table.add_row("shape", node.shape)
            table.add_row("terminated_time", node.terminated_time)
            table.add_row("update_count", str(node.update_count))
            table.add_row("slurm_state", node.slurm_state)
            table.add_row("slurm_reservation", node.slurm_reservation)
            table.add_row("slurm_up_time", str(node.slurm_up_time) if node.slurm_up_time is not None else "N/A")
            table.add_row("slurm_partition", node.slurm_partition)
            for hc_type in ["passive","active","multi_node"]:
                for hc_entry in db.get_extra_columns_per_hc():
                    table.add_row(f"{hc_type}_{hc_entry}", getattr(node, f"{hc_type}_{hc_type}_{hc_entry}"))

        console = rich.get_console()
        console.print(table)

def print_node_list(nodes, title):
    table = rich.table.Table(title=title)
    table.add_column("hostname", justify="left", no_wrap=True)
    table.add_column("status", justify="left")
    table.add_column("compute_status", justify="left")
    table.add_column("healthcheck_recommendation", justify="left")
    table.add_column("cluster_name", justify="left")
    table.add_column("memory_cluster_name", justify="left")
    table.add_column("ocid", justify="left")
    table.add_column("serial", justify="left")
    table.add_column("ip_address", justify="left")
    table.add_column("shape", justify="left")

    for node in nodes:        
        table.add_row(
            node.hostname, node.status, node.compute_status,node.healthcheck_recommendation, node.cluster_name,
            node.memory_cluster_name, str(node.ocid), node.serial,
            node.ip_address, node.shape
        )

    console = rich.get_console()
    console.print(table)


class InvalidField(Exception):
    def __init__(self, invalid_fields, valid_fields=None):
        self.invalid_fields = invalid_fields
        self.valid_fields = valid_fields

        if valid_fields:
            msg = f"Invalid field(s): {self.invalid_fields}. Valid choices: {sorted(self.valid_fields)}"
        else:
            msg = f"Invalid field(s): {self.invalid_fields}"

        super().__init__(msg)


class ListValidFields(Exception):
    """
    Kind of an abuse of the exception system. This should be raised when a
    field spec starts with "LIST"
    """

    def __init__(self, valid_fields):
        self.valid_fields = valid_fields
        super().__init__()

    def __str__(self):
        return "\n".join(sorted(self.valid_fields))


def parse_fields_spec(fields_spec):
    """
    For commands that want to control which fields are displayed, this function
    provides a specification for selecting the fields.

    If the spec is empty/None, a default list of fields is selected.
    If the spec starts with:
    * "ALL", all fields are selected.
    * "DEFAULT", a default set is selected.
    * "SIMPLE", all fields except those known to be multi-line are selected.

    From there, the list of fields can be further refined by listing additional
    fields after a '+' or '-' character. The '+' and '-' operators stay in
    effect until the end of the line or another operator is used.

    Examples:

    "DEFAULT,+rail_id,network_block_id,hpc_island,-cluster_name,shape"

        This will take the default list of fields, add rail_id,
        network_block_id, and hpc_island, and then remove cluster_name and
        shape.

    "serial,hostname,ip_address"

        This will only display the three listed fields.

    The ordering of fields may or may not be significant
    NOTE: It is expected that most of the display functions will honor the
    ordering of the fields. When displaying as "json", the field order is not
    honored.

    This function is agnostic to the argument parser in use. The caller is
    expected to handle the custom exception types and handle them
    appropriately.

    For example, if using the "click" argument parser, it might look like this:

        try:
            return display.parse_fields_spec(value)
        except display.ListValidFields as exc:
            click.echo(str(exc))
            raise SystemExit(0) from exc
        except display.InvalidField as exc:
            raise click.BadParameter(str(exc)) from exc

    """

    # Yeah, it's a lot of branches. Not uncommon for parsers.
    # pylint: disable=too-many-branches

	# Default list of fields
    fields_def = [
        "hostname",
        "healthcheck_recommendation",
        "status",
        "compute_status",
        "cluster_name",
        "memory_cluster_name",
        "ocid",
        "serial",
        "ip_address",
        "shape"
    ]

    fields_all = db.list_columns()
    valid_fields = set(fields_all)

    fields = []

    if fields_spec is None:
        fields = fields_def
    else:
        value = fields_spec.split(",")

        if value[0].lower() == "all":
            fields = fields_all
            value.pop(0)
        elif value[0].lower() == "default":
            fields = fields_def
            value.pop(0)
        elif value[0].lower() == "simple":
            # Only single-line fields
            fields = fields_all
            value.pop(0)
        elif value[0].lower() == "hc":
            # Only single-line fields
            fields_hc = [field for field in fields_all if "healthcheck_" in field]
            fields = fields_def + fields_hc
            value.pop(0)
        elif value[0].lower() == "list":
            raise ListValidFields(fields_all)

        op = "+"

        invalid_fields = []
        for field in value:
            if field[0] in ("-", "+"):
                op = field[0]
                field = field.lstrip("-+")

            if field not in valid_fields:
                invalid_fields.append(field)

            if op == "+":
                if field not in fields:
                    fields.append(field)
            else:
                try:
                    fields.remove(field)
                except ValueError:
                    pass

        if invalid_fields:
            raise InvalidField(invalid_fields, valid_fields=valid_fields)

    return fields


# oops, redefined "format", and "filter"
# pylint: disable=redefined-builtin


def display_nodes_as_json(nodes, fields, one_line=False, **ignored_kwargs):
    keys = set(fields) if fields else None
    node_dicts = [db.node_to_dict(node, keys) for node in nodes]
    if one_line:
        print(json.dumps(node_dicts))
    else:
        rich.get_console().print_json(json.dumps(node_dicts))


def display_nodes_as_csv(nodes, fields, show_header=True, **ignored_kwargs):
    node_dicts = [db.node_to_dict(node, fields) for node in nodes]
    writer = csv.DictWriter(sys.stdout, fieldnames=fields, dialect="unix")
    if show_header:
        writer.writeheader()
    writer.writerows(node_dicts)


def display_nodes_as_nodeset(nodes, **ignored_kwargs):
    click.echo(NodeSet.fromlist(node.hostname for node in nodes))


def display_nodes_as_table(nodes, fields, per_node=False, table_style=None, show_header=True, width=None):
    # I can't find any other way to make Rich honor the width arg
    if width:
        os.environ["COLUMNS"] = str(width)

    console = rich.get_console()

    # If stdout isn't a terminal, don't include any table borders. This
    # makes it easier to pipe to tools like grep
    if table_style is None:
        table_style = "box" if console.is_terminal else "none"

    style = {
        "lines": {"show_lines": True},
        "none":  {"show_lines": False, "box": None},
        "box":   {"show_lines": False},
    }[table_style]
    node_lists = (db.node_to_list(node, fields) for node in nodes)

    if per_node:
        # Each node gets its own table
        for node in node_lists:
            # TODO: Might be nice to have a header with the hostname
            table = rich.table.Table(show_header=False, **style)

            for field, value in zip(fields, node):
                safe_value = str(value) if value is not None else ""
                table.add_row(field, safe_value)

            console.print(table)
    else:
        table = rich.table.Table(show_header=show_header, **style)

        for field in fields:
            table.add_column(field, justify="left")

        for row in node_lists:
            safe_row = [str(v) if v is not None else "" for v in row]
            table.add_row(*safe_row)

        console.print(table)


def display_nodes(nodes, format, fields, table_style=None, one_line=False, show_header=True, width=None):
    """Dispatch function for the various 'display_nodes_as_*' functions"""

    if format == "json":
        display_nodes_as_json(nodes, fields, one_line=one_line)
    elif format == "csv":
        display_nodes_as_csv(nodes, fields, show_header=show_header)
    elif one_line:
        display_nodes_as_nodeset(nodes)
    else:
        per_node = format == "node"
        display_nodes_as_table(
            nodes, fields,
            per_node=per_node, table_style=table_style,
            show_header=show_header, width=width
        )
