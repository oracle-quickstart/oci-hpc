from concurrent.futures import ThreadPoolExecutor, as_completed
import click
import oci
from ClusterShell.NodeSet import NodeSet

from lib.database import get_all_nodes, get_controller_node, get_nodes_by_any
from lib.logger import logger
from lib.ociwrap import invoke_node_event_function, list_tagged_cluster_nodes


EVENT_TYPES = {
    "start": "com.oraclecloud.computeapi.launchinstance.end",
    "terminate": "com.oraclecloud.computeapi.terminateinstance.begin",
}
DEFAULT_EVENT_TYPE = "start"


def _invoke_one(function_id, node, event_type):
    if not node.ocid or not node.compartment_id:
        return node, False, "missing ocid or compartment_id"

    try:
        invoke_node_event_function(function_id, node, event_type)
    except oci.exceptions.ServiceError as exc:
        return node, False, str(exc)

    return node, True, None


def _node_identifiers(node):
    return {
        value for value in [
            getattr(node, "ocid", None),
            getattr(node, "ip_address", None),
            getattr(node, "hostname", None),
            getattr(node, "oci_name", None),
            getattr(node, "serial", None),
        ] if value
    }


def _get_tagged_oci_nodes(include_private_ip=False):
    controller = get_controller_node()
    if not controller:
        raise click.ClickException("Controller node was not found in the mgmt DB.")

    return list_tagged_cluster_nodes(
        controller.compartment_id,
        controller.cluster_name,
        controller.controller_name,
        include_private_ip=include_private_ip,
    )


def _get_nodes_by_any_db_then_oci(node_identifiers):
    identifiers = set(NodeSet(node_identifiers))
    nodes_list = get_nodes_by_any(identifiers)
    found_identifiers = set()

    for node in nodes_list:
        found_identifiers.update(_node_identifiers(node))

    missing_identifiers = identifiers - found_identifiers
    if not missing_identifiers:
        return nodes_list

    found_ocids = {node.ocid for node in nodes_list if node.ocid}
    for node in _get_tagged_oci_nodes(include_private_ip=True):
        if missing_identifiers.intersection(_node_identifiers(node)):
            if node.ocid not in found_ocids:
                nodes_list.append(node)
                found_ocids.add(node.ocid)

    return nodes_list


def _get_sync_nodes():
    oci_nodes = _get_tagged_oci_nodes()
    db_nodes = get_all_nodes()
    oci_node_ocids = {node.ocid for node in oci_nodes if node.ocid}
    db_node_ocids = {node.ocid for node in db_nodes if node.ocid}
    start_nodes = [node for node in oci_nodes if node.ocid not in db_node_ocids]
    terminate_nodes = [node for node in db_nodes if node.ocid not in oci_node_ocids]
    return start_nodes, terminate_nodes


def _invoke_nodes(function_id, nodes_list, event_type, workers):
    failed = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_invoke_one, function_id, node, event_type)
            for node in nodes_list
        ]
        for future in as_completed(futures):
            node, success, error = future.result()
            if success:
                click.echo(f"Invoked function for {node.hostname or node.ocid}")
                continue

            failed.append(node)
            logger.error("Function invoke failed for %s: %s", node.ocid, error)

    return failed


@click.command("fn-invoke")
@click.pass_obj
@click.option("--all", "all_nodes", is_flag=True, help="Invoke for all matching OCI nodes.")
@click.option("--sync", is_flag=True, help="Replay missing start and terminate events by comparing OCI and the mgmt DB.")
@click.option(
    "--nodes",
    required=False,
    help="Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names).",
)
@click.option(
    "--function-id",
    required=False,
    help="Oracle Functions function OCID. Defaults to write_node_function_ocid in mgmt.ini.",
)
@click.option(
    "--event-type",
    required=False,
    default=DEFAULT_EVENT_TYPE,
    type=click.Choice(EVENT_TYPES.keys()),
    show_default=True,
    help="Event type to send in the function payload when using --nodes.",
)
@click.option(
    "--workers",
    required=False,
    default=10,
    show_default=True,
    help="Maximum number of parallel function invocations.",
)
def fn_invoke(cfg, all_nodes, sync, nodes, function_id, event_type, workers):
    """Invoke the Oracle function for node launch/termination."""
    selected_modes = [bool(all_nodes), bool(sync), bool(nodes)]
    if sum(selected_modes) != 1:
        raise click.UsageError("Specify exactly one of --all, --sync, or --nodes.")
    if event_type != DEFAULT_EVENT_TYPE and not nodes:
        raise click.UsageError("--event-type terminate can only be used with --nodes.")

    if workers < 1:
        raise click.ClickException("--workers must be at least 1.")

    function_id = function_id or cfg.get("write_node_function_ocid")
    if not function_id:
        raise click.ClickException(
            "Function OCID is required. Use --function-id or set write_node_function_ocid in mgmt.ini."
        )

    if all_nodes:
        nodes_list = _get_tagged_oci_nodes()
        oci_event_type = EVENT_TYPES["start"]
    elif sync:
        start_nodes, terminate_nodes = _get_sync_nodes()
        failed = []
        if start_nodes:
            click.echo(f"Replaying start event for {len(start_nodes)} node(s).")
            failed.extend(_invoke_nodes(function_id, start_nodes, EVENT_TYPES["start"], workers))
        if terminate_nodes:
            click.echo(f"Replaying terminate event for {len(terminate_nodes)} node(s).")
            failed.extend(_invoke_nodes(function_id, terminate_nodes, EVENT_TYPES["terminate"], workers))
        if not start_nodes and not terminate_nodes:
            raise click.ClickException("No nodes to sync.")
        if failed:
            raise click.ClickException(f"Function invoke failed for {len(failed)} node(s).")
        return
    else:
        nodes_list = _get_nodes_by_any_db_then_oci(nodes)
        oci_event_type = EVENT_TYPES[event_type]

    if not nodes_list:
        raise click.ClickException("No matching nodes found.")

    failed = _invoke_nodes(function_id, nodes_list, oci_event_type, workers)
    if failed:
        raise click.ClickException(f"Function invoke failed for {len(failed)} node(s).")
