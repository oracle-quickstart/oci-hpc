import click
import re
from lib.cli import completion
from lib.database import get_nodes_by_any, get_recommendation_node_groups, join_nodes_lists
from lib.functions import get_slurm_state, run_configure, scan_host_api_logic, run_reset_gpus
from lib.ociwrap import list_instance_maintenance_events, run_reboot, run_terminate, run_tag, run_enable_instance_rdma_plugins
from lib.cli.recommendations.display import print_ime_node_list, print_node_list


from lib.logger import logger
from datetime import datetime, timedelta, timezone

from ClusterShell.NodeSet import NodeSet

# ------------------------
# Click Commands
# ------------------------

@click.group()
def recom():
    """Get information about nodes."""
    pass


def _unique_nodes(nodes):
    """Keep one row per node while preserving the input order."""
    return [node for node in {node.ocid or node.hostname: node for node in nodes}.values()]


def _utc_datetime(value):
    """Parse stored HC and OCI timestamps as UTC for freshness comparisons."""
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)


def _maintenance_blocks_values(recommendation, state, window, now):
    """Apply the list policy to an IME, whether read from mgmt or live OCI."""
    if recommendation == "TERMINATE":
        return True
    if recommendation not in ("DOWNTIME_REPAIR", "LIVE_REPAIR"):
        return False
    if state in ("STARTED", "PROCESSING"):
        return True
    if state != "SCHEDULED":
        return False
    window_start = _utc_datetime(window)
    return window_start is None or window_start <= now + timedelta(minutes=5)


def _maintenance_blocks_actions(node, now):
    """Check whether the IME stored on a mgmt node currently holds actions."""
    return _maintenance_blocks_values(
        node.ime_recommendation,
        node.maintenance_event_lifecycle_state,
        node.maintenance_event_time_window_start,
        now,
    )


def _selected_candidates(groups, unreachable, unconfigured, healthcheck):
    """Select action candidates for the same mode flags in list and run."""
    all_modes = not (unreachable or unconfigured or healthcheck)
    unreachable_nodes = groups["unreachable"] if all_modes or unreachable else []
    unconfigured_nodes = (
        join_nodes_lists(groups["failing_to_start"], groups["slurm_unconfigured"])
        if all_modes or unconfigured else []
    )
    return {
        "reboot": _unique_nodes(unreachable_nodes + (groups["reboot"] if all_modes or healthcheck else [])),
        "reset_gpus": groups["reset_gpus"] if all_modes or healthcheck else [],
        "terminate": groups["terminate"] if all_modes or healthcheck else [],
        "enable_rdma": groups["enable_instance_rdma_plugins"] if all_modes or healthcheck else [],
        "reconfigure": _unique_nodes(unconfigured_nodes),
    }


def _requested_ocids(nodes):
    """Resolve every --nodes identifier; reject partial or empty matches."""
    requested = {identifier for identifier in NodeSet(nodes)}
    matches = get_nodes_by_any(NodeSet(nodes))
    known = {
        str(value)
        for node in matches
        for value in (node.hostname, node.ip_address, node.ocid, node.serial, node.oci_name, node.alternate_hostname)
        if value
    }
    missing = requested - known
    if missing:
        raise click.BadParameter(f"Unknown node identifier(s): {', '.join(sorted(missing))}", param_hint="--nodes")
    return {node.ocid for node in matches}


def _filter_groups(groups, ocids):
    """Apply --nodes to every recommendation category, including reconfigure."""
    if ocids is None:
        return groups
    return {name: [node for node in nodes if node.ocid in ocids] for name, nodes in groups.items()}


_HC_ACTIONS = {
    "reboot": "Reboot",
    "reset_gpus": "Reset_GPU",
    "terminate": "Terminate",
    "enable_rdma": "Enable_Instance_RDMA_Plugins",
}


def _event_recommendation(event):
    """Map a live active OCI event to the recommendation used by list."""
    if event.lifecycle_state not in ("SCHEDULED", "STARTED", "PROCESSING"):
        return None
    return {
        "TERMINATE": "TERMINATE",
        "DOWNTIME_HOST_MAINTENANCE": "DOWNTIME_REPAIR",
        "LIVE_HOST_MAINTENANCE": "LIVE_REPAIR",
    }.get(event.display_name)


def _hold_reason(node, action, now, live_events=()):
    """Explain why an action must wait for OCI or a post-maintenance HC."""
    if _maintenance_blocks_actions(node, now):
        return f"stored OCI {node.ime_recommendation} event is {node.maintenance_event_lifecycle_state}"

    for event in live_events:
        recommendation = _event_recommendation(event)
        if _maintenance_blocks_values(
            recommendation, event.lifecycle_state, event.time_window_start, now
        ):
            return f"OCI {recommendation} event is {event.lifecycle_state}"

    if node.passive_healthcheck_recommendation != _HC_ACTIONS.get(action):
        return None
    checked = _utc_datetime(node.passive_healthcheck_last_time)
    finished_times = []
    if node.maintenance_event_lifecycle_state == "SUCCEEDED":
        finished_times.append(_utc_datetime(node.maintenance_event_time_finished))
    finished_times.extend(
        _utc_datetime(event.time_finished)
        for event in live_events
        if event.lifecycle_state == "SUCCEEDED"
        and event.display_name in ("DOWNTIME_HOST_MAINTENANCE", "LIVE_HOST_MAINTENANCE")
    )
    if any(finished and (checked is None or checked <= finished) for finished in finished_times):
        return "passive healthcheck predates completed OCI maintenance"
    return None


def _partition_actions(candidates, now, live_events_by_ocid=None):
    """Choose one action per node and split actionable nodes from held nodes."""
    available = {action: [] for action in candidates}
    held = {}
    selected = set()
    # A node must not be rebooted and terminated in the same run.
    for action in ("terminate", "reboot", "reset_gpus", "enable_rdma", "reconfigure"):
        for node in _unique_nodes(candidates[action]):
            node_id = node.ocid or node.hostname
            if node_id in selected:
                continue
            selected.add(node_id)
            events = live_events_by_ocid.get(node.ocid, ()) if live_events_by_ocid is not None else ()
            reason = _hold_reason(node, action, now, events)
            if reason:
                held[node_id] = (node, action, reason)
            else:
                available[action].append(node)
    return available, held


def _live_events_for(nodes):
    """Read all OCI events for candidate compartments, failing before mutations."""
    nodes = _unique_nodes(nodes)
    if not nodes:
        return {}
    if any(not node.compartment_id or not node.ocid for node in nodes):
        raise click.ClickException("Cannot verify OCI maintenance events for a node without compartment or instance ID")
    wanted = {node.ocid for node in nodes}
    events_by_ocid = {}
    for compartment_id in sorted({node.compartment_id for node in nodes}):
        try:
            events = list_instance_maintenance_events(compartment_id, strict=True)
        except Exception as exc:
            raise click.ClickException(f"OCI maintenance event lookup failed: {exc}") from exc
        for event in events:
            if event.instance_id in wanted:
                events_by_ocid.setdefault(event.instance_id, []).append(event)
    return events_by_ocid


def _slurm_allows_action(node, state=None):
    """Require a drained or down node with no allocated or completing work."""
    state = node.slurm_state if state is None else state
    components = {part.strip().lower() for part in re.split(r"[+,]", state or "")}
    return bool(components & {"drain", "down"}) and not bool(
        components & {"allocated", "mixed", "completing", "comp"}
    )


@recom.command()
@click.option('--healthcheck', is_flag=True, help='Show Healthcheck Recommendations with OCI maintenance holds.', default=False)
@click.option('--unreachable', is_flag=True, help='Only show the unreachable nodes.', default=False)
@click.option('--unconfigured', is_flag=True, help='Only show the nodes failing to start.', default=False)
@click.option('--unreachable_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=30)
@click.option('--unconfigured_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=60)
def list(unreachable, unconfigured, healthcheck, unreachable_timeout, unconfigured_timeout):
    """List all the nodes with recommendations."""
    groups = get_recommendation_node_groups(
        timedelta(minutes=unreachable_timeout),
        timedelta(minutes=unconfigured_timeout),
    )
    all_recommendations = not (unreachable or unconfigured or healthcheck)
    candidates = _selected_candidates(groups, unreachable, unconfigured, healthcheck)
    selected_nodes = _unique_nodes([node for nodes in candidates.values() for node in nodes])
    selected_ocids = {node.ocid for node in selected_nodes}
    ime_repair_nodes = groups["ime_repair"]
    ime_terminate_nodes = groups["ime_terminate"]
    if not all_recommendations:
        ime_repair_nodes = [node for node in ime_repair_nodes if node.ocid in selected_ocids]
        ime_terminate_nodes = [node for node in ime_terminate_nodes if node.ocid in selected_ocids]

    now = datetime.now(timezone.utc)
    held_nodes = [node for node in ime_repair_nodes if _maintenance_blocks_actions(node, now)]
    scheduled_nodes = [node for node in ime_repair_nodes if not _maintenance_blocks_actions(node, now)]
    available, held_actions = _partition_actions(candidates, now)
    reboot_nodes = available["reboot"]
    reset_gpu_nodes = available["reset_gpus"]
    terminate_nodes = available["terminate"]
    enable_rdma_nodes = available["enable_rdma"]
    reconfigure_nodes = available["reconfigure"]

    if reboot_nodes:
        print_node_list(reboot_nodes, "Nodes to Reboot")
        click.echo(NodeSet(','.join(node.hostname for node in reboot_nodes)))
    if reset_gpu_nodes:
        print_node_list(reset_gpu_nodes, "Nodes to Reset GPUs")
        click.echo(NodeSet(','.join(node.hostname for node in reset_gpu_nodes)))
    if terminate_nodes:
        print_node_list(terminate_nodes, "Nodes to Terminate")
        click.echo(NodeSet(','.join(node.hostname for node in terminate_nodes)))
    if enable_rdma_nodes:
        print_node_list(enable_rdma_nodes, "Nodes to Enable Instance RDMA Plugins")
        click.echo(NodeSet(','.join(node.hostname for node in enable_rdma_nodes)))
    if reconfigure_nodes:
        print_node_list(reconfigure_nodes, "Nodes to Reconfigure")
        click.echo(NodeSet(','.join(node.hostname for node in reconfigure_nodes)))

    if not reboot_nodes and not reset_gpu_nodes:
        if candidates["reboot"] or candidates["reset_gpus"]:
            logger.info("Reboot or GPU reset recommendations are held pending OCI maintenance or a fresh healthcheck\n")
        else:
            logger.info("There are no nodes requiring reboot or GPU reset\n")
    if not terminate_nodes:
        if candidates["terminate"]:
            logger.info("Healthcheck termination is held pending OCI maintenance or a fresh healthcheck\n")
        else:
            logger.info("There are no passive-healthcheck termination recommendations\n")
    if not enable_rdma_nodes:
        if candidates["enable_rdma"]:
            logger.info("Instance RDMA plugin enablement is held pending OCI maintenance or a fresh healthcheck\n")
        else:
            logger.info("There are no nodes requiring Instance RDMA plugin enablement\n")
    if not reconfigure_nodes:
        if candidates["reconfigure"]:
            logger.info("Reconfiguration is held by OCI maintenance\n")
        else:
            logger.info("There are no nodes in need of reconfiguration\n")

    recheck_nodes = _unique_nodes([
        node for node, _, reason in held_actions.values()
        if reason == "passive healthcheck predates completed OCI maintenance"
    ])
    if recheck_nodes:
        print_node_list(recheck_nodes, "Awaiting post-maintenance passive healthcheck")
        click.echo(NodeSet(','.join(node.hostname for node in recheck_nodes)))

    if held_nodes:
        print_ime_node_list(held_nodes, "OCI maintenance active or imminent")
        click.echo(NodeSet(','.join(node.hostname for node in held_nodes)))
    if scheduled_nodes:
        print_ime_node_list(scheduled_nodes, "OCI maintenance scheduled")
        click.echo(NodeSet(','.join(node.hostname for node in scheduled_nodes)))
    if ime_terminate_nodes:
        print_ime_node_list(ime_terminate_nodes, "OCI termination recommended")
        click.echo(NodeSet(','.join(node.hostname for node in ime_terminate_nodes)))

    if held_nodes or scheduled_nodes or ime_terminate_nodes:
        click.echo("mgmt recommendations run rechecks OCI maintenance before acting.\n")

    available_nodes=scan_host_api_logic()
    if not available_nodes:
        logger.info("There are no available nodes in the dedicated pool\n")
    for shape in available_nodes.keys():
        click.echo(f"There are {available_nodes[shape]} available nodes of shape {shape} in your pool. running the recommandations will not add the nodes\n")


@recom.command()
@click.pass_obj
@click.option('--nodes', required=False, help='Comma separated list of nodes (IP Addresses, hostnames, OCID\'s, serials or oci names)', shell_complete=completion.complete_node_identifiers)
@click.option('--healthcheck', is_flag=True, help='', default=False)
@click.option('--unreachable', is_flag=True, help='Get full information about the nodes.', default=False)
@click.option('--unconfigured', is_flag=True, help='Get full information about the nodes.', default=False)
@click.option('--unreachable_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=30)
@click.option('--unconfigured_timeout', type=int, help='Timeout in minutes before a node is considered unreachable.', default=60)
@click.option('--dry-run', is_flag=True, help='Show actions and skips without changing nodes or OCI resources.')
def run(cfg, unreachable, unconfigured, healthcheck, nodes, unreachable_timeout, unconfigured_timeout, dry_run):
    """Apply the same recommendations as list after a live OCI maintenance check."""
    groups = get_recommendation_node_groups(
        timedelta(minutes=unreachable_timeout),
        timedelta(minutes=unconfigured_timeout),
    )
    if nodes:
        groups = _filter_groups(groups, _requested_ocids(nodes))
    candidates = _selected_candidates(groups, unreachable, unconfigured, healthcheck)
    candidate_nodes = _unique_nodes([node for items in candidates.values() for node in items])
    if not candidate_nodes:
        click.echo("No recommendations match the selected arguments.")
        return

    # Verify every candidate before planning; a failed OCI lookup aborts the run.
    live_events = _live_events_for(candidate_nodes)
    available, held = _partition_actions(candidates, datetime.now(timezone.utc), live_events)
    for action, action_nodes in available.items():
        if action == "reconfigure":
            continue
        for node in action_nodes[:]:
            if not _slurm_allows_action(node):
                action_nodes.remove(node)
                held[node.ocid or node.hostname] = (
                    node, action, f"Slurm state {node.slurm_state!r} is not drained or down"
                )

    for node, action, reason in held.values():
        click.echo(f"Skipping {node.hostname} ({action}): {reason}")

    labels = {
        "terminate": "tag and terminate",
        "reboot": "reboot",
        "reset_gpus": "reset GPUs",
        "enable_rdma": "enable instance RDMA plugins",
        "reconfigure": "reconfigure",
    }
    for action in ("terminate", "reboot", "reset_gpus", "enable_rdma", "reconfigure"):
        action_nodes = available[action]
        if action_nodes:
            verb = "Would" if dry_run else "Will"
            click.echo(f"{verb} {labels[action]}: {NodeSet(','.join(node.hostname for node in action_nodes))}")
    if dry_run:
        return

    def ready(node, action):
        """Recheck OCI and, for disruptive actions, live Slurm before acting."""
        try:
            events = _live_events_for([node]).get(node.ocid, ())
        except click.ClickException as exc:
            click.echo(f"Skipping {node.hostname} ({action}): {exc}")
            return False
        reason = _hold_reason(node, action, datetime.now(timezone.utc), events)
        if reason:
            click.echo(f"Skipping {node.hostname} ({action}): {reason}")
            return False
        if action != "reconfigure":
            live_state = get_slurm_state().get(node.hostname, {}).get("state")
            if not _slurm_allows_action(node, live_state or "unknown"):
                click.echo(
                    f"Skipping {node.hostname} ({action}): live Slurm state "
                    f"{live_state or 'unknown'!r} is not safely drained or down"
                )
                return False
        return True

    for node in available["terminate"]:
        if ready(node, "terminate"):
            run_tag(node)
            run_terminate(node)
    for node in available["reboot"]:
        if ready(node, "reboot"):
            run_reboot(node, False)
    for node in available["reset_gpus"]:
        if ready(node, "reset_gpus"):
            run_reset_gpus(node, clush_parallel_executions=cfg["clush_parallel_executions"])
    for node in available["enable_rdma"]:
        if ready(node, "enable_rdma"):
            run_enable_instance_rdma_plugins(node)
    ready_to_configure = [node for node in available["reconfigure"] if ready(node, "reconfigure")]
    if ready_to_configure:
        run_configure(ready_to_configure, clush_parallel_executions=cfg["clush_parallel_executions"])

    available_nodes = scan_host_api_logic()
    for shape, count in available_nodes.items():
        click.echo(f"There are {count} available nodes of shape {shape} in your pool.")
