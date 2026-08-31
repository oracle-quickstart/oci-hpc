import click

from lib.ociwrap import get_available_memory_fabric_targets


UNKNOWN_HPC_ISLAND_VALUES = {"", "None", "none", "null"}


def split_fabric_ids(fabric):
    if not fabric:
        return []
    return [item.strip() for item in fabric.split(",") if item.strip()]


def _normalize_hpc_island_id(hpc_island_id):
    if hpc_island_id is None:
        return None
    hpc_island_id = str(hpc_island_id).strip()
    if hpc_island_id in UNKNOWN_HPC_ISLAND_VALUES:
        return None
    return hpc_island_id


def resolve_cluster_hpc_island(nodes, cluster):
    hpc_islands = sorted({
        _normalize_hpc_island_id(getattr(node, "hpc_island", None))
        for node in nodes
    } - {None})
    if len(hpc_islands) > 1:
        raise click.ClickException(
            f"Cluster {cluster} has nodes in multiple HPC islands: {', '.join(hpc_islands)}. "
            "Specify --compute-hpc-island-id."
        )
    if not hpc_islands:
        return None
    return hpc_islands[0]


def _fabric_hpc_island_id(fabric_target):
    hpc_island_id = fabric_target.get("compute_hpc_island_id")
    if hpc_island_id:
        return _normalize_hpc_island_id(hpc_island_id)
    return _normalize_hpc_island_id(
        getattr(fabric_target.get("fabric"), "compute_hpc_island_id", None)
    )


def _validate_targets_match_hpc_island(targets, expected_hpc_island_id, cluster=None):
    expected_hpc_island_id = _normalize_hpc_island_id(expected_hpc_island_id)
    if expected_hpc_island_id is None:
        return

    mismatches = [
        f"{target['ocid']} ({_fabric_hpc_island_id(target) or 'unknown'})"
        for target in targets
        if _fabric_hpc_island_id(target) != expected_hpc_island_id
    ]
    if mismatches:
        scope = f"cluster {cluster}" if cluster else "requested cluster"
        raise click.ClickException(
            "GPU memory fabric(s) are not in the same HPC island as "
            f"{scope} ({expected_hpc_island_id}): {', '.join(mismatches)}"
        )


def _validate_targets_have_single_hpc_island(targets):
    hpc_islands = sorted({
        _fabric_hpc_island_id(target)
        for target in targets
    } - {None})
    if len(hpc_islands) > 1:
        raise click.ClickException(
            "Selected GPU memory fabrics span multiple HPC islands: "
            f"{', '.join(hpc_islands)}. Specify --compute-hpc-island-id."
        )
    if not hpc_islands and len(targets) > 1:
        raise click.ClickException(
            "Could not determine HPC island for selected GPU memory fabrics; "
            "specify --compute-hpc-island-id."
        )


def _filter_targets_by_minimum_gmc_size(targets, minimum_gmc_size):
    if minimum_gmc_size is None:
        return targets
    return [
        target for target in targets
        if int(target.get("available", 0) or 0) >= minimum_gmc_size
    ]


def resolve_fabric_targets(
    controller,
    fabric=None,
    all_fabrics=False,
    compute_local_block_id=None,
    compute_network_block_id=None,
    compute_hpc_island_id=None,
    current_hpc_island_id=None,
    require_single_hpc_island=False,
    minimum_gmc_size=None,
    cluster=None,
):
    fabric_ids = split_fabric_ids(fabric)
    current_hpc_island_id = _normalize_hpc_island_id(current_hpc_island_id)
    compute_hpc_island_id = _normalize_hpc_island_id(compute_hpc_island_id)
    if current_hpc_island_id and compute_hpc_island_id and current_hpc_island_id != compute_hpc_island_id:
        raise click.ClickException(
            f"Cluster {cluster or ''} is in HPC island {current_hpc_island_id}, "
            f"but --compute-hpc-island-id is {compute_hpc_island_id}"
        )

    scope_filters = {
        "compute_local_block_id": compute_local_block_id,
        "compute_network_block_id": compute_network_block_id,
        "compute_hpc_island_id": compute_hpc_island_id,
    }
    selected_scope_filters = {
        key: value for key, value in scope_filters.items() if value
    }
    selector_count = sum([
        bool(fabric_ids),
        all_fabrics,
        *[bool(value) for value in selected_scope_filters.values()],
    ])

    if selector_count > 1:
        raise click.ClickException(
            "Use only one of --fabric, --all, --compute-local-block-id, "
            "--compute-network-block-id, or --compute-hpc-island-id"
        )

    if all_fabrics or selected_scope_filters:
        effective_scope_filters = dict(selected_scope_filters)
        if current_hpc_island_id and not effective_scope_filters.get("compute_hpc_island_id"):
            effective_scope_filters["compute_hpc_island_id"] = current_hpc_island_id
        targets = get_available_memory_fabric_targets(
            controller.tenancy_id,
            controller.compartment_id,
            all_available=True,
            **effective_scope_filters,
        )
        targets = _filter_targets_by_minimum_gmc_size(targets, minimum_gmc_size)
        if not targets:
            if minimum_gmc_size is not None:
                raise click.ClickException(
                    f"No available GPU memory fabrics found with at least {minimum_gmc_size} AVAILABLE hosts"
                )
            raise click.ClickException("No available GPU memory fabrics found")
        _validate_targets_match_hpc_island(targets, current_hpc_island_id, cluster=cluster)
        if require_single_hpc_island:
            _validate_targets_have_single_hpc_island(targets)
        return targets

    if fabric_ids:
        targets = get_available_memory_fabric_targets(
            controller.tenancy_id,
            controller.compartment_id,
            fabric_ids=fabric_ids,
        )
        targets = _filter_targets_by_minimum_gmc_size(targets, minimum_gmc_size)
        if not targets and minimum_gmc_size is not None:
            raise click.ClickException(
                f"No requested GPU memory fabrics have at least {minimum_gmc_size} AVAILABLE hosts"
            )
        _validate_targets_match_hpc_island(targets, current_hpc_island_id, cluster=cluster)
        if require_single_hpc_island:
            _validate_targets_have_single_hpc_island(targets)
        return targets

    return []


def resolve_target_count(count, fabric_target):
    if count not in (None, 0):
        return int(count)

    available = int(fabric_target.get("available", 0) or 0)
    if available <= 0:
        raise click.ClickException(
            f"No available hosts found for GPU memory fabric {fabric_target['ocid']}"
        )
    return available


def resolve_memory_cluster_name(cluster, memorycluster, fabric_ocid, multiple=False):
    suffix = fabric_ocid[-5:]
    if memorycluster and not multiple:
        return memorycluster
    if memorycluster:
        return f"{memorycluster}_{suffix}"
    return f"{cluster}_{suffix}"
