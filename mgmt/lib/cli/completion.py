from __future__ import annotations

"""Dynamic completion helpers for runtime-backed mgmt CLI values.

Click already handles command, subcommand, and static option completion well.
This module exists only for values that must be fetched at runtime from the DB
or OCI, such as node names, clusters, images, and field values.
"""

import json
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable

from click.shell_completion import CompletionItem
from sqlalchemy.inspection import inspect as sqlalchemy_inspect

import lib.database as db
from lib.ociwrap import get_memory_fabrics, list_custom_images


NODE_IDENTIFIER_FIELDS = ("hostname", "ip_address", "serial", "ocid", "oci_name")
NODE_FIELD_ALIASES = ("healthcheck_recommendation",)
COLUMN_SPECIAL_VALUES = ("ALL", "DEFAULT", "SIMPLE", "HC", "LIST")
COMPLETION_CACHE_PATH = Path(tempfile.gettempdir()) / "mgmt_completion_cache.json"
COMPLETION_CACHE_TTL_SECONDS = 10
NODE_FIELD_FALLBACK_VALUES = {
    "controller_status": [
        "configuring",
        "terminating",
        "waiting_for_info",
        "configured",
        "terminated",
        "reconfiguring",
    ],
    "status": ["starting", "terminating", "terminated", "running", "unreachable"],
    "compute_status": ["configuring", "configured", "starting", "terminating", "stopped"],
    "role": ["compute", "controller", "login", "monitoring"],
}


def _normalize_values(values: Iterable) -> list[str]:
    normalized = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            normalized.append(str(value).lower())
        else:
            normalized.append(str(value))
    return sorted(set(normalized))


def _read_completion_cache() -> dict:
    try:
        with COMPLETION_CACHE_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        return {}
    return {}


def _write_completion_cache(cache: dict) -> None:
    try:
        tmp_path = COMPLETION_CACHE_PATH.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle, sort_keys=True)
        tmp_path.replace(COMPLETION_CACHE_PATH)
    except OSError:
        return


def _cached_values(cache_key: str, loader: Callable[[], Iterable], ttl_seconds: int = COMPLETION_CACHE_TTL_SECONDS) -> list[str]:
    now = time.time()
    cache = _read_completion_cache()
    entry = cache.get(cache_key)
    if isinstance(entry, dict):
        timestamp = entry.get("timestamp")
        values = entry.get("values")
        if isinstance(timestamp, (int, float)) and isinstance(values, list) and (now - timestamp) < ttl_seconds:
            return _normalize_values(values)

    values = _normalize_values(loader())
    cache[cache_key] = {
        "timestamp": now,
        "values": values,
    }
    _write_completion_cache(cache)
    return values


def _prefix_matches(values: Iterable, incomplete: str) -> list[CompletionItem]:
    incomplete = incomplete or ""
    items = []
    for value in _normalize_values(values):
        if not incomplete or value.startswith(incomplete):
            items.append(CompletionItem(value))
    return items


def _csv_matches(values: Iterable, incomplete: str, suffix: str = "") -> list[CompletionItem]:
    prefix = ""
    current = incomplete
    if "," in incomplete:
        prefix, current = incomplete.rsplit(",", 1)

    items = []
    for value in _normalize_values(values):
        candidate = f"{value}{suffix}"
        if current and not candidate.startswith(current):
            continue
        full_value = f"{prefix},{candidate}" if prefix else candidate
        items.append(CompletionItem(full_value))
    return items


def _safe_completion(fn, *args, **kwargs) -> list[CompletionItem]:
    try:
        return fn(*args, **kwargs)
    except Exception:
        return []


def _node_query_label_map():
    query = db.get_nodes_with_latest_healthchecks()
    label_map = {
        col["name"]: col["expr"]
        for col in query.column_descriptions
        if "expr" in col and col["name"]
    }
    return query, label_map


def _distinct_node_field_values(field_name: str, limit: int = 100) -> list[str]:
    query, label_map = _node_query_label_map()
    column = label_map.get(field_name)
    fallback_values = NODE_FIELD_FALLBACK_VALUES.get(field_name, [])
    if column is None:
        return fallback_values
    rows = (
        query.with_entities(column)
        .filter(column.is_not(None))
        .distinct()
        .limit(limit)
        .all()
    )
    values = [row[0] for row in rows]
    return _normalize_values([*values, *fallback_values])


def _node_identifier_values() -> list[str]:
    values = []
    for node in db.get_all_nodes():
        for field_name in NODE_IDENTIFIER_FIELDS:
            values.append(getattr(node, field_name, None))
    return _normalize_values(values)


def _node_field_names() -> list[str]:
    return sorted(set(db.list_columns() + list(NODE_FIELD_ALIASES)))


def _field_key_value_matches(keys: Iterable[str], value_lookup, incomplete: str) -> list[CompletionItem]:
    prefix = ""
    current = incomplete
    if "," in incomplete:
        prefix, current = incomplete.rsplit(",", 1)

    if "=" in current:
        key, current_value = current.split("=", 1)
        values = _normalize_values(value_lookup(key))
        items = []
        for value in values:
            if current_value and not value.startswith(current_value):
                continue
            full_value = f"{key}={value}"
            items.append(CompletionItem(f"{prefix},{full_value}" if prefix else full_value))
        return items

    items = []
    for key in sorted(set(keys)):
        candidate = f"{key}="
        if current and not candidate.startswith(current):
            continue
        items.append(CompletionItem(f"{prefix},{candidate}" if prefix else candidate))
    return items


def complete_clusters(ctx, param, incomplete):
    return _safe_completion(
        _prefix_matches,
        _cached_values("clusters", db.get_clusters),
        incomplete,
    )


def complete_memory_clusters(ctx, param, incomplete):
    def _values():
        query, label_map = _node_query_label_map()
        column = label_map.get("memory_cluster_name")
        if column is None:
            return []
        return [
            row[0]
            for row in query.with_entities(column)
            .filter(column.is_not(None))
            .distinct()
            .all()
        ]

    return _safe_completion(
        _prefix_matches,
        _cached_values("memory_clusters", _values),
        incomplete,
    )


def complete_node_identifiers(ctx, param, incomplete):
    return _safe_completion(
        _csv_matches,
        _cached_values("node_identifiers", _node_identifier_values),
        incomplete,
    )


def complete_node_fields(ctx, param, incomplete):
    def _lookup(field_name: str) -> list[str]:
        return _cached_values(f"node_field_values:{field_name}", lambda: _distinct_node_field_values(field_name))

    return _safe_completion(
        _field_key_value_matches,
        _node_field_names(),
        _lookup,
        incomplete,
    )


def complete_display_columns(ctx, param, incomplete):
    def _values():
        return list(COLUMN_SPECIAL_VALUES) + db.list_columns()

    prefix = ""
    current = incomplete
    if "," in incomplete:
        prefix, current = incomplete.rsplit(",", 1)

    operator = ""
    if current.startswith(("+", "-")):
        operator = current[0]
        current = current[1:]

    items = []
    for value in _normalize_values(_values()):
        candidate = f"{operator}{value}"
        if current and not value.startswith(current):
            continue
        full_value = f"{prefix},{candidate}" if prefix else candidate
        items.append(CompletionItem(full_value))
    return items


def complete_configurations_all(ctx, param, incomplete):
    return _safe_completion(
        _prefix_matches,
        _cached_values("configurations:all", lambda: [config.name for config in db.get_all_configs("all")]),
        incomplete,
    )


def complete_configuration_partitions(ctx, param, incomplete):
    return _safe_completion(
        _prefix_matches,
        _cached_values("configuration_partitions", lambda: [config.partition for config in db.get_all_configs("all")]),
        incomplete,
    )


def complete_configurations_compute(ctx, param, incomplete):
    return _safe_completion(
        _prefix_matches,
        _cached_values("configurations:compute", lambda: [config.name for config in db.get_all_configs("compute")]),
        incomplete,
    )


def complete_configurations_login(ctx, param, incomplete):
    return _safe_completion(
        _prefix_matches,
        _cached_values("configurations:login", lambda: [config.name for config in db.get_all_configs("login")]),
        incomplete,
    )


def complete_configuration_fields(ctx, param, incomplete):
    def _fields():
        return [
            column.key
            for column in sqlalchemy_inspect(db.Configurations).mapper.column_attrs
            if column.key not in {"id", "name"}
        ]

    return _safe_completion(
        _field_key_value_matches,
        _fields(),
        lambda _key: [],
        incomplete,
    )


def complete_images(ctx, param, incomplete):
    def _values():
        compartment = ctx.params.get("compartment")
        if not compartment:
            controller = db.get_controller_node()
            if controller is None:
                return []
            compartment = controller.compartment_id

        images = list_custom_images(compartment)
        values = []
        for image in images:
            values.extend([image.id, image.display_name])
        return values

    compartment = ctx.params.get("compartment") or "controller"
    return _safe_completion(
        _prefix_matches,
        _cached_values(f"images:{compartment}", _values),
        incomplete,
    )


def complete_fabrics(ctx, param, incomplete):
    def _values():
        controller = db.get_controller_node()
        if controller is None:
            return []
        fabrics = get_memory_fabrics(controller.tenancy_id, controller.compartment_id)
        return [fabric[0].id for fabric in fabrics]

    return _safe_completion(
        _prefix_matches,
        _cached_values("fabrics", _values),
        incomplete,
    )
