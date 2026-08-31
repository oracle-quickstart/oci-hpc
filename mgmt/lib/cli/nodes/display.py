import csv
import json
import os
import sys

import click
import lib.database as db
import rich
import rich.table
import rich.tree
from ClusterShell.NodeSet import NodeSet
from lib.logger import logger

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
            table.add_row("alternate_hostname", node.alternate_hostname)
            table.add_row("hpc_island", node.hpc_island)
            table.add_row("image_id", node.image_id)
            table.add_row("instance_type", node.instance_type)
            table.add_row("last_time_reachable", node.last_time_reachable)
            table.add_row("network_block_id", node.network_block_id)
            table.add_row("memory_cluster_id", node.memory_cluster_id)
            table.add_row("oci_name", node.oci_name)
            table.add_row("ocid", node.ocid)
            table.add_row("rack_id", node.rack_id)
            table.add_row("rack_index", str(node.rack_index))
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
                    table.add_row(f"{hc_type}_{hc_entry}", getattr(node, f"{hc_type}_{hc_entry}"))

        console = rich.get_console()
        console.print(table)

def print_node_list(nodes, title):
    table = rich.table.Table(title=title)
    table.add_column("hostname", justify="left", no_wrap=True)
    table.add_column("status", justify="left")
    table.add_column("compute_status", justify="left")
    table.add_column("healthcheck_recommendation", justify="left")
    table.add_column("cluster_name", justify="left")
    table.add_column("memory_cluster_id", justify="left")
    table.add_column("ocid", justify="left")
    table.add_column("serial", justify="left")
    table.add_column("ip_address", justify="left")
    table.add_column("shape", justify="left")
    table.add_column("alternate_hostname", justify="left")

    for node in nodes:
        table.add_row(
            node.hostname, node.status, node.compute_status,node.healthcheck_recommendation, node.cluster_name,
            node.memory_cluster_id, str(node.ocid), node.serial,
            node.ip_address, node.shape, node.alternate_hostname
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


def parse_sort_spec(sort_spec):
    """
    Parse a comma-separated list of fields for sorting.

    Returns the requested sort field names in the user-specified order.
    """

    valid_fields = set(db.list_columns())

    if sort_spec is None:
        return []

    sort_fields = []
    invalid_fields = []
    for field in [field.strip() for field in sort_spec.split(",") if field.strip()]:
        if field not in valid_fields:
            invalid_fields.append(field)
        elif field not in sort_fields:
            sort_fields.append(field)

    if invalid_fields:
        raise InvalidField(invalid_fields, valid_fields=valid_fields)

    return sort_fields


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
        "memory_cluster_id",
        "ocid",
        "serial",
        "ip_address",
        "shape",
        "alternate_hostname"
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


def _normalize_sort_value(val):
    """
    Normalize values so mixed/nullable fields can be sorted consistently.
    """

    if val is None:
        return (1, "")

    if isinstance(val, bool):
        return (0, int(val))

    if isinstance(val, int):
        return (0, val)

    return (0, str(val).casefold())


def sort_nodes(nodes, sort_fields):
    """Sort nodes in-memory by the requested fields."""

    if not sort_fields:
        return nodes

    return sorted(
        nodes,
        key=lambda node: tuple(
            _normalize_sort_value(getattr(node, field, None)) for field in sort_fields
        ),
    )


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


# Nesting levels for the RDMA topology tree, outermost first. The leaf level
# (rack_id, or memory_cluster_id when populated) is chosen per-node by
# _leaf_group(), so it is not part of this tuple.
TOPOLOGY_LEVELS = ("hpc_island", "network_block_id", "rail_id")


def _topo_label(val):
    """Return a display-safe label for a topology value (None -> 'none')."""
    return "none" if val is None else str(val)


def _topo_sort_key(val):
    """Sort group keys, pushing None/empty values to the end."""
    if not val:
        return (1, "")
    return (0, str(val))


def _count_topo_leaves(branch):
    """Count nodes held at the bottom of a nested dict/list topology tree."""
    if isinstance(branch, list):
        return len(branch)
    return sum(_count_topo_leaves(child) for child in branch.values())


def _leaf_group(node):
    """Return (field_name, value) for the leaf-level topology grouping.

    Nodes with memory-cluster metadata use memory_cluster_id; everything else
    uses rack_id.
    """
    memory_cluster_id = getattr(node, "memory_cluster_id", None)
    normalized_memory_cluster_id = str(memory_cluster_id or "").strip()
    if normalized_memory_cluster_id and normalized_memory_cluster_id.lower() != "none":
        return ("memory_cluster_id", memory_cluster_id)
    return ("rack_id", getattr(node, "rack_id", None))


def _index_ranges(idxs):
    """Compact a sorted list of ints into range notation.

    Examples: [0,1,2,4,5,17] -> '0-2,4-5,17'; [0] -> '0'.
    """
    if not idxs:
        return ""
    idxs = sorted(set(idxs))
    ranges = []
    start = prev = idxs[0]
    for x in idxs[1:]:
        if x == prev + 1:
            prev = x
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = x
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


# ComputeHost-driven topology (full mode). Colors signal host state:
#   occupied + unhealthy  -> degraded (orange)
#   no instance + healthy -> free capacity, missing from DB (blue)
#   no instance + unhealthy -> unusable (grey)
# Only an explicit HEALTHY counts as healthy; anything else (including OCI's
# UNKNOWN_ENUM_VALUE) is treated as unhealthy/unknown and never shown as free.
HOST_HEALTH_HEALTHY = "HEALTHY"
HOST_HEALTH_UNHEALTHY = "UNHEALTHY"
TOPO_DEGRADED_COLOR = "dark_orange"
TOPO_AVAILABLE_COLOR = "blue"
TOPO_UNUSABLE_COLOR = "grey50"
TOPO_MAINTENANCE_COLOR = "yellow"


def _empty_host_availability(empty_hosts):
    """Map (island, netblock, rail) -> (available, unavailable) empty-host counts.

    A slot counts as available when its host lifecycle_state is AVAILABLE and
    it is healthy; any other empty host state counts as unavailable. Hosts have
    no rack metadata, so availability is aggregated at rail (local_block_id)
    granularity.
    """
    result = {}
    for host in empty_hosts:
        key = (
            getattr(host, "hpc_island_id", None),
            getattr(host, "network_block_id", None),
            getattr(host, "local_block_id", None),
        )
        available, unavailable = result.get(key, (0, 0))
        if getattr(host, "lifecycle_state", None) == "AVAILABLE" and _host_is_healthy(host):
            available += 1
        else:
            unavailable += 1
        result[key] = (available, unavailable)
    return result


def _load_full_compute_data(hpc_nodes, controller):
    """Single ComputeHost-API fetch powering the full topology view.

    Returns (host_by_instance, empty_hosts, mc_status, mc_to_fabric, gmf_status):
      host_by_instance: instance_id -> ComputeHost (occupied)
      empty_hosts:      unprovisioned hosts scoped to the displayed nodes'
                        (hpc_island_id, network_block_id) pairs
      mc_status:        memory_cluster_id -> per-fabric host lifecycle counts
      mc_to_fabric:     memory_cluster_id -> gpu_memory_fabric_id
      gmf_status:       gpu_memory_fabric_id -> per-fabric host lifecycle counts
    All empty when the API is unavailable. Fetching hosts once (instead of via
    both get_host_api_dict and get_memory_fabrics) avoids a duplicate fetch.
    """
    host_by_instance = {}
    empty_hosts = []
    mc_status = {}
    mc_to_fabric = {}
    gmf_status = {}
    try:
        from lib.ociwrap import get_host_api_dict
        if not (controller and controller.tenancy_id):
            return host_by_instance, empty_hosts, mc_status, mc_to_fabric, gmf_status
        node_by_ocid = {n.ocid: n for n in hpc_nodes}
        scope_pairs = {
            (getattr(n, "hpc_island", None), getattr(n, "network_block_id", None))
            for n in hpc_nodes
        }
        fabric_counts = {}
        for host in get_host_api_dict(controller.compartment_id, controller.tenancy_id):
            gmf = getattr(host, "gpu_memory_fabric_id", None)
            state = getattr(host, "lifecycle_state", None)
            if gmf is not None:
                counts = fabric_counts.setdefault(gmf, {})
                counts[state] = counts.get(state, 0) + 1
            instance_id = getattr(host, "instance_id", None)
            if instance_id:
                host_by_instance[instance_id] = host
                node = node_by_ocid.get(instance_id)
                if node is not None and gmf is not None:
                    mc = getattr(node, "memory_cluster_id", None)
                    if mc:
                        mc_to_fabric.setdefault(mc, gmf)
            elif (getattr(host, "hpc_island_id", None),
                  getattr(host, "network_block_id", None)) in scope_pairs:
                empty_hosts.append(host)
        gmf_status = fabric_counts
        for mc, gmf in mc_to_fabric.items():
            mc_status[mc] = fabric_counts.get(gmf, {})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot load compute host data: %s", exc)
    return host_by_instance, empty_hosts, mc_status, mc_to_fabric, gmf_status


def _availability_text(counts):
    """Availability string for a host-state counts dict (or NA marker)."""
    if not counts:
        return _colorize("O: NA, A: NA, R: NA, U: NA, P: NA", TOPO_UNUSABLE_COLOR)
    occupied = int(counts.get('OCCUPIED', 0) or 0)
    available = int(counts.get('AVAILABLE', 0) or 0)
    repair = int(counts.get('REPAIR', 0) or 0)
    unavailable = int(counts.get('UNAVAILABLE', 0) or 0)
    provisioning = int(counts.get('PROVISIONING', 0) or 0)
    a_str = _colorize(f"A: {available:2d}", "bold green" if available > 0 else None)
    return (f"O: {occupied:2d}, {a_str}, R: {repair:2d}, "
            f"U: {unavailable:2d}, P: {provisioning:2d}")


def _memory_cluster_group_info(mc_status, mc_id):
    """Availability string for a memory cluster (or NA marker)."""
    return _availability_text(mc_status.get(mc_id))


def _topology_status_legend():
    """Legend for the host-state letters shown in status/full views."""
    return (
        "[bold]Status legend:[/bold] O: Occupied, A: Available, R: Repair, "
        "U: Unavailable, P: Provisioning, NA: no data"
    )


def _topology_color_legend(mode="compact"):
    """Legend explaining the colors used in the topology views.

    compact mode does not query the host API, so it only tracks active
    maintenance (yellow). status also checks host health (orange), while full
    additionally shows free-slot availability (blue/grey).
    """
    hierarchy = (
        f"{_colorize('island', 'cyan')} "
        f"{_colorize('netblock', 'blue')} "
        f"{_colorize('rail', 'magenta')} "
        f"{_colorize('rack/memcluster', 'dark_red')} "
        f"{_colorize('gmf', 'green')} = {_colorize('hierarchy level', 'bright_black')}"
    )
    if mode == "full":
        entries = (
            f"{hierarchy}, "
            f"{_colorize('orange = unhealthy host', TOPO_DEGRADED_COLOR)}, "
            f"{_colorize('blue = available host', TOPO_AVAILABLE_COLOR)}, "
            f"{_colorize('grey = unavailable host', TOPO_UNUSABLE_COLOR)}, "
            f"{_colorize('yellow = active maintenance', TOPO_MAINTENANCE_COLOR)}"
        )
    elif mode == "status":
        entries = (
            f"{hierarchy}, "
            f"{_colorize('orange = at least one unhealthy host', TOPO_DEGRADED_COLOR)}, "
            f"{_colorize('yellow = at least one host with maintenance events', TOPO_MAINTENANCE_COLOR)}"
        )
    else:
        entries = (
            f"{hierarchy}, "
            f"{_colorize('yellow = at least one host with maintenance events', TOPO_MAINTENANCE_COLOR)}"
        )
    return f"[bold]Color legend:[/bold] {entries}"


def _host_is_healthy(host):
    return host is not None and getattr(host, "health", None) == HOST_HEALTH_HEALTHY


def _host_is_unhealthy(host):
    return host is not None and getattr(host, "health", None) == HOST_HEALTH_UNHEALTHY


# Maintenance lifecycle states that still matter (upcoming/in-progress).
ACTIVE_MAINTENANCE_STATES = {"SCHEDULED", "PROCESSING", "STARTED"}


def _node_has_active_maintenance(node):
    """True when the node has an active (upcoming/in-progress) maintenance."""
    return str(getattr(node, "maintenance_event_lifecycle_state", "")).upper() in ACTIVE_MAINTENANCE_STATES


def _node_has_maintenance(node):
    """True when the node has any stored maintenance event (any state)."""
    return bool(
        getattr(node, "maintenance_event_id", None)
        or getattr(node, "maintenance_event_display_name", None)
    )


def _topo_group_color(nodes, host_by_instance=None):
    """Color for a topology group: orange when any node is degraded (host
    API), else yellow when any node has an active DB maintenance event."""
    maintenance = False
    for node in nodes:
        if host_by_instance is not None and _host_is_unhealthy(
            host_by_instance.get(getattr(node, "ocid", None))
        ):
            return TOPO_DEGRADED_COLOR
        if _node_has_active_maintenance(node):
            maintenance = True
    if maintenance:
        return TOPO_MAINTENANCE_COLOR
    return None


def _colorize(text, color):
    return f"[{color}]{text}[/{color}]" if color else str(text)


def _topo_key_sort(k):
    """Sort typed (kind, value) topology keys: by kind, then value."""
    return (k[0], _topo_sort_key(k[1]))


def _topo_full_place(root, host, node, mc_to_fabric):
    """Insert one host/node into the full-mode nested topology tree.

    Coordinates come from the ComputeHost (primary) and fall back to the
    database node when no host is available.
    """
    if host is not None:
        island = getattr(host, "hpc_island_id", None)
        netblock = getattr(host, "network_block_id", None)
        rail = getattr(host, "local_block_id", None)
        gmf = getattr(host, "gpu_memory_fabric_id", None)
    else:
        island = getattr(node, "hpc_island", None)
        netblock = getattr(node, "network_block_id", None)
        rail = getattr(node, "rail_id", None)
        gmf = None

    rail_branch = root.setdefault(island, {}).setdefault(netblock, {}).setdefault(rail, {})

    if node is None:
        if gmf is not None:
            rail_branch.setdefault(("gmf", gmf), {}).setdefault(("empty", None), []).append(host)
        else:
            rail_branch.setdefault(("no_instance", None), []).append(host)
        return

    mc = getattr(node, "memory_cluster_id", None)
    is_memcluster = bool(mc) and str(mc).strip().lower() not in ("", "none")
    if is_memcluster:
        if gmf is None:
            gmf = mc_to_fabric.get(mc)
        if gmf is None:
            logger.warning(
                "Memory cluster node %s (%s) has no GMF, grouping under gmf none",
                getattr(node, "hostname", None), mc,
            )
        rail_branch.setdefault(("gmf", gmf), {}).setdefault(("gmc", mc), []).append(node)
    else:
        rail_branch.setdefault(("rack", getattr(node, "rack_id", None)), []).append(node)


def _topo_full_node_text(node, host):
    body = f"{node.hostname} - {node.serial} - {node.ocid}"
    if _host_is_unhealthy(host):
        return _colorize(f"{body} (DEGRADED)", TOPO_DEGRADED_COLOR)
    if _node_has_active_maintenance(node):
        return _colorize(body, TOPO_MAINTENANCE_COLOR)
    return body


def _topo_full_host_text(host):
    host_id = getattr(host, "id", None) or "?"
    state = getattr(host, "lifecycle_state", None) or "?"
    health = getattr(host, "health", None) or "?"
    body = f"{host_id} - {state} - {health}"
    if state == "AVAILABLE" and _host_is_healthy(host):
        return _colorize(body, TOPO_AVAILABLE_COLOR)
    return _colorize(body, TOPO_UNUSABLE_COLOR)


def _format_maintenance(name, state, code, window, degraded):
    parts = [f"maintenance: {name} [{state}]"]
    if code:
        parts.append(code)
    if window:
        parts.append(f"@ {window}")
    color = TOPO_DEGRADED_COLOR if degraded else TOPO_MAINTENANCE_COLOR
    return _colorize(" ".join(parts), color)


def _maintenance_event_text(node, degraded=False):
    """Format the node's DB-stored maintenance event as a sub-line."""
    return _format_maintenance(
        getattr(node, "maintenance_event_display_name", None) or "maintenance",
        getattr(node, "maintenance_event_lifecycle_state", None) or "?",
        getattr(node, "maintenance_event_error_code", None),
        getattr(node, "maintenance_event_time_window_start", None),
        degraded,
    )


def _maintenance_event_text_from_oci(event, degraded=False):
    """Format an OCI maintenance event (list result) as a sub-line."""
    return _format_maintenance(
        getattr(event, "display_name", None) or "maintenance",
        getattr(event, "lifecycle_state", None) or "?",
        None,
        getattr(event, "time_window_start", None),
        degraded,
    )


# Event state priority for the active maintenance shown on a degraded host
# (lower is preferred). The filter keeps only active events
# (SCHEDULED/STARTED/PROCESSING), ignoring FAILED, CANCELED and SUCCEEDED;
# when a degraded host has no active event left, the latest one is used
# instead.
_MAINTENANCE_EVENT_STATE_PRIORITY = {
    "SCHEDULED": 0,
    "STARTED": 1,
    "PROCESSING": 2,
}


def _maintenance_event_select_key(event):
    return (
        _MAINTENANCE_EVENT_STATE_PRIORITY.get(
            str(getattr(event, "lifecycle_state", "")).upper(), 99
        ),
        str(getattr(event, "time_window_start", "") or ""),
        str(getattr(event, "id", "") or ""),
    )


def _maintenance_event_completion_time(event):
    """Latest completion-ish time for an event, for picking the newest one."""
    for attr in ("time_finished", "time_window_start"):
        value = getattr(event, attr, None)
        if value:
            return str(value)
    return ""


def _load_oci_maintenance_by_instance(controller):
    """Map instance_id -> maintenance event for the OCI fallback.

    Reuses the active-maintenance filtering (SCHEDULED/STARTED/PROCESSING),
    ignoring FAILED, CANCELED and SUCCEEDED events. When a degraded host has
    no active events left after the filter, the filter is bypassed for that
    host and its latest maintenance event is used instead. Empty when the API
    is unavailable.
    """
    best_active = {}
    latest_events = {}

    from lib.ociwrap import list_instance_maintenance_events

    try:
        events = list_instance_maintenance_events(controller.compartment_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot load maintenance events: %s", exc)
        return {}
    for event in events:
        state = str(getattr(event, "lifecycle_state", "")).upper()
        instance_id = getattr(event, "instance_id", None)
        if not instance_id:
            continue
        current = latest_events.get(instance_id)
        if (
            current is None
            or _maintenance_event_completion_time(event)
            > _maintenance_event_completion_time(current)
        ):
            latest_events[instance_id] = event
        if state in ACTIVE_MAINTENANCE_STATES:
            current = best_active.get(instance_id)
            if (
                current is None
                or _maintenance_event_select_key(event)
                < _maintenance_event_select_key(current)
            ):
                best_active[instance_id] = event
    by_instance = dict(best_active)
    for instance_id, event in latest_events.items():
        by_instance.setdefault(instance_id, event)
    return by_instance


def _topo_full_render_nodes(leaf, nodes, host_by_instance, show_index, oci_maintenance=None):
    """Append occupied nodes to a leaf with their maintenance sub-line.

    Degraded hosts (unhealthy via the host API) render orange with a sub-line
    for the DB record (any state), else the OCI fallback. Healthy hosts show
    only an active DB maintenance event (yellow); they never use the OCI
    fallback.
    """
    for node in nodes:
        host = host_by_instance.get(getattr(node, "ocid", None))
        prefix = f"{node.rack_index}: " if show_index and node.rack_index is not None else ""
        entry = leaf.add(prefix + _topo_full_node_text(node, host))
        if _host_is_unhealthy(host):
            if _node_has_maintenance(node):
                entry.add(_maintenance_event_text(node, degraded=True))
            elif oci_maintenance:
                event = oci_maintenance.get(getattr(node, "ocid", None))
                if event is not None:
                    entry.add(_maintenance_event_text_from_oci(event, degraded=True))
        elif _node_has_active_maintenance(node):
            entry.add(_maintenance_event_text(node, degraded=False))


def _topo_full_render_rack(b3, key, nodes, host_by_instance, oci_maintenance=None):
    ordered = sorted(nodes, key=lambda n: (n.rack_index is None, n.rack_index))
    idxs = [n.rack_index for n in ordered if len(ordered) > 1 and n.rack_index is not None]
    idx_text = f", idx {_index_ranges(idxs)}" if idxs else ""
    leaf = b3.add(f"[dark_red]rack[/dark_red] {_topo_label(key[1])} ({len(ordered)}{idx_text})")
    _topo_full_render_nodes(leaf, ordered, host_by_instance,
                            show_index=len(ordered) > 1,
                            oci_maintenance=oci_maintenance)


def _topo_full_render_gmf(b3, key, gmf_branch, gmf_status, host_by_instance, oci_maintenance=None):
    gmf_b = b3.add(
        f"[green]gmf[/green] {_topo_label(key[1])} "
        f"({_count_topo_leaves(gmf_branch)}, {_availability_text(gmf_status.get(key[1]))})"
    )
    for sub_key in sorted(gmf_branch, key=_topo_key_sort):
        children = gmf_branch[sub_key]
        if sub_key[0] == "empty":
            leaf = gmf_b.add(f"no instance ({len(children)})")
            for host in sorted(children, key=lambda h: getattr(h, "display_name", "") or ""):
                leaf.add(_topo_full_host_text(host))
        else:
            nodes = sorted(children, key=lambda n: (n.rack_index is None, n.rack_index))
            leaf = gmf_b.add(
                f"[dark_red]memcluster[/dark_red] {_topo_label(sub_key[1])} ({len(nodes)})"
            )
            _topo_full_render_nodes(leaf, nodes, host_by_instance,
                                    show_index=False,
                                    oci_maintenance=oci_maintenance)


def _topo_full_render_no_instance(b3, hosts):
    leaf = b3.add(f"no instance ({len(hosts)})")
    for host in sorted(hosts, key=lambda h: getattr(h, "display_name", "") or ""):
        leaf.add(_topo_full_host_text(host))


def _render_topology_full(tree, hpc_nodes):
    node_by_ocid = {n.ocid: n for n in hpc_nodes}
    controller = db.get_controller_node()
    (host_by_instance, empty_hosts, _, mc_to_fabric, gmf_status) = _load_full_compute_data(hpc_nodes, controller)

    degraded_missing_db = [
        n for n in hpc_nodes
        if _host_is_unhealthy(host_by_instance.get(getattr(n, "ocid", None)))
        and not _node_has_maintenance(n)
    ]
    oci_maintenance = {}
    if degraded_missing_db and controller:
        oci_maintenance = _load_oci_maintenance_by_instance(controller)

    root = {}
    matched = set()
    for host in host_by_instance.values():
        node = node_by_ocid.get(getattr(host, "instance_id", None))
        if node is None:
            continue
        matched.add(node.ocid)
        _topo_full_place(root, host, node, mc_to_fabric)
    for host in empty_hosts:
        _topo_full_place(root, host, None, mc_to_fabric)
    for node in hpc_nodes:
        if node.ocid in matched:
            continue
        _topo_full_place(root, None, node, mc_to_fabric)

    for island in sorted(root, key=_topo_sort_key):
        ib = root[island]
        b1 = tree.add(f"[cyan]island[/cyan] {_topo_label(island)} ({_count_topo_leaves(ib)})")
        for netblock in sorted(ib, key=_topo_sort_key):
            nb = ib[netblock]
            b2 = b1.add(f"[blue]netblock[/blue] {_topo_label(netblock)} ({_count_topo_leaves(nb)})")
            for rail in sorted(nb, key=_topo_sort_key):
                rb = nb[rail]
                b3 = b2.add(f"[magenta]rail[/magenta] {_topo_label(rail)} ({_count_topo_leaves(rb)})")
                for key in sorted(rb, key=_topo_key_sort):
                    if key[0] == "rack":
                        _topo_full_render_rack(b3, key, rb[key], host_by_instance, oci_maintenance)
                    elif key[0] == "no_instance":
                        _topo_full_render_no_instance(b3, rb[key])
                    else:
                        _topo_full_render_gmf(b3, key, rb[key], gmf_status, host_by_instance, oci_maintenance)


def _render_topology_compact(tree, hpc_nodes, mode, mc_status, empty_hosts=None, hosts_available=False, host_by_instance=None):
    rail_avail = _empty_host_availability(empty_hosts) if hosts_available else None
    root = {}
    for node in hpc_nodes:
        branch = root
        for level in TOPOLOGY_LEVELS:
            branch = branch.setdefault(getattr(node, level, None), {})
        leaf = _leaf_group(node)
        branch.setdefault(leaf, []).append(node)

    for island in sorted(root, key=_topo_sort_key):
        island_branch = root[island]
        b1 = tree.add(f"[cyan]island[/cyan] {_topo_label(island)} ({_count_topo_leaves(island_branch)})")
        for netblock in sorted(island_branch, key=_topo_sort_key):
            nb_branch = island_branch[netblock]
            b2 = b1.add(f"[blue]netblock[/blue] {_topo_label(netblock)} ({_count_topo_leaves(nb_branch)})")
            for rail in sorted(nb_branch, key=_topo_sort_key):
                rail_branch = nb_branch[rail]
                rail_label = f"[magenta]rail[/magenta] {_topo_label(rail)} ({_count_topo_leaves(rail_branch)})"
                has_rack = any(key[0] == "rack_id" for key in rail_branch)
                if has_rack and rail_avail is not None:
                    available, unavailable = rail_avail.get((island, netblock, rail), (0, 0))
                    rail_label += f" A: {available}, U: {unavailable}"
                rail_color = _topo_group_color(
                    [n for leaf in rail_branch.values() for n in leaf],
                    host_by_instance,
                )
                if rail_color:
                    rail_label = _colorize(rail_label, rail_color)
                b3 = b2.add(rail_label)
                for leaf_key in sorted(rail_branch, key=_topo_key_sort):
                    field_name, leaf_val = leaf_key
                    rack_nodes = sorted(
                        rail_branch[leaf_key],
                        key=lambda n: (n.rack_index is None, n.rack_index),
                    )
                    is_mc = field_name == "memory_cluster_id"
                    leaf_label = "memcluster" if is_mc else "rack"
                    leaf_prefix = f"[dark_red]{leaf_label}[/dark_red] {_topo_label(leaf_val)}"
                    if is_mc:
                        group_info = _memory_cluster_group_info(mc_status, leaf_val) if mode == "status" else None
                    else:
                        idxs = [n.rack_index for n in rack_nodes if len(rack_nodes) > 1 and n.rack_index is not None]
                        group_info = f"idx {_index_ranges(idxs)}" if idxs else None
                    number_of_hosts = len(rack_nodes)
                    count_text = str(number_of_hosts)
                    if group_info:
                        count_text = f"{count_text}, {group_info}"
                    hostset = NodeSet.fromlist(n.hostname for n in rack_nodes)
                    color = _topo_group_color(rack_nodes, host_by_instance)
                    if is_mc:
                        if mode == "status" and group_info:
                            b3.add(
                                f"{leaf_prefix} ({group_info}) "
                                f"{_colorize(f'({number_of_hosts})', color)} "
                                f"{_colorize(hostset, color)}"
                            )
                        else:
                            b3.add(
                                f"{leaf_prefix} "
                                f"{_colorize(f'({number_of_hosts}) {hostset}', color)}"
                            )
                    else:
                        b3.add(f"{leaf_prefix} {_colorize(f'({count_text})  {hostset}', color)}")


def display_nodes_as_topology(nodes, mode="compact", **ignored_kwargs):
    """Render nodes as a hierarchical RDMA topology tree.

    compact/status: hpc_island > network_block_id > rail_id > rack_id (or
    memory_cluster_id), nodes ordered by rack_index.

    status also queries the ComputeHost API: memory clusters show per-fabric
    O/A/R/U/P host-state counts, and non-GMC rails show empty-slot
    availability (A = available, U = unavailable) on the rail line.

    full: ComputeHost-API driven. hpc_island > network_block_id > rail_id >
    gpu_memory_fabric (GMF) > memory_cluster_id (GMC). Free host slots that
    have no database node are shown under their GMF: healthy slots render blue
    (available), unhealthy ones grey. Occupied nodes on an unhealthy host
    render orange (degraded). Topology coordinates come from the ComputeHost
    API and fall back to the database when a host is unavailable.

    VM-shaped nodes are grouped under a top-level 'vm-nodes' branch.
    """

    vm_nodes = [n for n in nodes if (n.shape or "").startswith("VM")]
    hpc_nodes = [n for n in nodes if not (n.shape or "").startswith("VM")]

    tree = rich.tree.Tree(f"[bold]Topology[/bold] ({len(nodes)} nodes)")

    if vm_nodes:
        vm_branch = tree.add(f"[bold green]vm-nodes[/bold green] ({len(vm_nodes)})")
        if mode in ("compact", "status"):
            vm_branch.add(str(NodeSet.fromlist(n.hostname for n in vm_nodes)))
        else:
            for node in sorted(vm_nodes, key=lambda n: n.hostname or ""):
                vm_branch.add(node.hostname)

    if mode == "full":
        _render_topology_full(tree, hpc_nodes)
    elif mode == "status":
        controller = db.get_controller_node()
        host_by_instance, empty_hosts, mc_status, _, _ = _load_full_compute_data(hpc_nodes, controller)
        hosts_available = bool(host_by_instance or empty_hosts)
        _render_topology_compact(
            tree, hpc_nodes, mode, mc_status,
            empty_hosts=empty_hosts, hosts_available=hosts_available,
            host_by_instance=host_by_instance,
        )
    else:
        _render_topology_compact(tree, hpc_nodes, mode, {})

    console = rich.get_console()
    console.print(tree)
    if mode in ("status", "full"):
        console.print(_topology_status_legend())
    if console.color_system is not None:
        console.print(_topology_color_legend(mode))
