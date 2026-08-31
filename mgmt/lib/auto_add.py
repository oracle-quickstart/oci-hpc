import json

from lib.database import get_controller_node, get_nodes_by_cluster
from lib.logger import logger
from lib.ociwrap import run_add, run_add_memory_fabric


AUTO_ADD_CONFIG_PATH = "/config/mgmt/auto_add_nodes.json"


def _is_gb_shape(shape):
    return "GPU.GB" in shape


def _normalize_shape_configs(hpc_island_id, shapes):
    if isinstance(shapes, str):
        shapes = [shapes]
    if isinstance(shapes, list):
        shapes = {shape: {} for shape in shapes}
    if not isinstance(shapes, dict) or not shapes:
        logger.error("HPC island %s has no configured shapes", hpc_island_id)
        return {}

    normalized_shapes = {}
    for shape, shape_config in shapes.items():
        if not isinstance(shape, str) or not shape.strip():
            logger.error("HPC island %s contains an invalid shape", hpc_island_id)
            continue
        if shape_config is None:
            shape_config = {}
        if not isinstance(shape_config, dict):
            logger.error(
                "HPC island %s shape %s must use a JSON object for its settings",
                hpc_island_id,
                shape,
            )
            continue

        if _is_gb_shape(shape) and "minimum_available_nodes" not in shape_config:
            logger.error(
                "HPC island %s GB shape %s requires minimum_available_nodes",
                hpc_island_id,
                shape,
            )
            continue
        try:
            minimum_available_nodes = int(shape_config.get("minimum_available_nodes", 1))
        except (TypeError, ValueError):
            logger.error(
                "HPC island %s shape %s has an invalid minimum_available_nodes",
                hpc_island_id,
                shape,
            )
            continue
        if minimum_available_nodes <= 0:
            logger.error(
                "HPC island %s shape %s minimum_available_nodes must be positive",
                hpc_island_id,
                shape,
            )
            continue

        target_size = shape_config.get("target_size")
        if target_size is not None:
            try:
                target_size = int(target_size)
            except (TypeError, ValueError):
                logger.error(
                    "HPC island %s shape %s has an invalid target_size",
                    hpc_island_id,
                    shape,
                )
                continue
            if target_size < 0:
                logger.error(
                    "HPC island %s shape %s target_size cannot be negative",
                    hpc_island_id,
                    shape,
                )
                continue

        normalized_shapes[shape.strip()] = {
            "minimum_available_nodes": minimum_available_nodes,
            "target_size": target_size,
        }

    return normalized_shapes


def load_auto_add_config(config_path=AUTO_ADD_CONFIG_PATH):
    try:
        with open(config_path, "r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        logger.debug("Auto-add config %s does not exist; auto-add is disabled", config_path)
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not read auto-add config %s: %s", config_path, exc)
        return {}

    if not isinstance(config, dict):
        logger.error("Auto-add config %s must contain a JSON object", config_path)
        return {}
    if not config.get("enabled", True):
        logger.debug("Auto-add is disabled in %s", config_path)
        return {}

    hpc_islands = config.get("hpc_islands", {})
    if not isinstance(hpc_islands, dict):
        logger.error("Auto-add config hpc_islands must be a JSON object")
        return {}

    mappings = {}
    for hpc_island_id, island_config in hpc_islands.items():
        if not hpc_island_id or not isinstance(island_config, dict):
            logger.error("Invalid auto-add config for HPC island %s", hpc_island_id)
            continue

        cluster = island_config.get("cluster")
        shapes = island_config.get("shapes", [])
        if not isinstance(cluster, str) or not cluster.strip():
            logger.error("HPC island %s has no valid cluster", hpc_island_id)
            continue
        normalized_shapes = _normalize_shape_configs(hpc_island_id, shapes)
        if not normalized_shapes:
            continue

        mappings[hpc_island_id] = {
            "cluster": cluster.strip(),
            "shapes": normalized_shapes,
        }

    return mappings


def _matching_cluster_nodes(cluster_nodes, shape, hpc_island_id):
    return [
        node
        for node in cluster_nodes
        if getattr(node, "role", None) == "compute"
        and getattr(node, "shape", None) == shape
        and getattr(node, "hpc_island", None) == hpc_island_id
        and getattr(node, "controller_name", None)
    ]


def _auto_add_gb_memory_fabrics(
    matching_nodes,
    shape,
    shape_config,
    hpc_island_id,
    cluster,
    completed_actions,
):
    from lib.cli.clusters.commands.gmf import (
        resolve_fabric_targets,
        resolve_memory_cluster_name,
        resolve_target_count,
    )

    controller = get_controller_node()
    if controller is None:
        logger.error("Refusing to auto-add GB nodes: no controller was found")
        return

    try:
        fabric_targets = resolve_fabric_targets(
            controller,
            all_fabrics=True,
            current_hpc_island_id=hpc_island_id,
            cluster=cluster,
        )
    except Exception as exc:
        logger.debug(
            "No eligible GPU memory fabrics for cluster %s in HPC island %s: %s",
            cluster,
            hpc_island_id,
            exc,
        )
        return

    minimum_available_nodes = shape_config["minimum_available_nodes"]
    multiple_fabrics = len(fabric_targets) > 1
    for fabric_target in fabric_targets:
        fabric = fabric_target.get("fabric")
        lifecycle_state = str(getattr(fabric, "lifecycle_state", "")).upper()
        if lifecycle_state != "AVAILABLE":
            logger.warning(
                "Skipping GPU memory fabric %s because lifecycle state is %s",
                fabric_target.get("ocid"),
                lifecycle_state or "unknown",
            )
            continue

        try:
            total_available = resolve_target_count(None, fabric_target)
        except Exception as exc:
            logger.error(
                "Could not determine available hosts for GPU memory fabric %s: %s",
                fabric_target.get("ocid"),
                exc,
            )
            continue
        available_by_shape = fabric_target.get("available_by_shape", {})
        try:
            available = int(available_by_shape.get(shape, 0) or 0)
        except (TypeError, ValueError, AttributeError):
            available = 0
        if available <= 0:
            logger.warning(
                "Skipping GPU memory fabric %s: no available hosts of shape %s",
                fabric_target["ocid"],
                shape,
            )
            continue
        if available != total_available:
            logger.warning(
                "Skipping GPU memory fabric %s: %d of %d available hosts match shape %s",
                fabric_target["ocid"],
                available,
                total_available,
                shape,
            )
            continue
        if available < minimum_available_nodes:
            logger.info(
                "Skipping GB auto-add for cluster %s: GPU memory fabric %s in HPC island %s "
                "has %d available %s node(s), below per-GMF threshold %d",
                cluster,
                fabric_target["ocid"],
                hpc_island_id,
                available,
                shape,
                minimum_available_nodes,
            )
            continue

        memory_cluster_name = resolve_memory_cluster_name(
            cluster,
            None,
            fabric_target["ocid"],
            multiple=multiple_fabrics,
        )
        target_size = shape_config["target_size"]
        if target_size is None:
            target_size = available
        logger.info(
            "Adding %d available %s node(s) from GPU memory fabric %s as GMC %s",
            available,
            shape,
            fabric_target["ocid"],
            memory_cluster_name,
        )
        try:
            run_add_memory_fabric(
                matching_nodes,
                controller,
                available,
                fabric_target["ocid"],
                memory_cluster_name,
                compute_cluster_name=cluster,
                targetsize=target_size,
            )
        except SystemExit as exc:
            logger.error("GB auto-add failed for GMC %s: %s", memory_cluster_name, exc)
            continue
        except Exception as exc:
            logger.exception("GB auto-add failed for GMC %s: %s", memory_cluster_name, exc)
            continue

        completed_actions.append({
            "type": "memory_fabric",
            "hpc_island_id": hpc_island_id,
            "shape": shape,
            "cluster": cluster,
            "memory_fabric_id": fabric_target["ocid"],
            "memory_cluster": memory_cluster_name,
            "count": available,
            "target_size": target_size,
        })


def auto_add_available_nodes(available_by_hpc_island, config_path=AUTO_ADD_CONFIG_PATH):
    mappings = load_auto_add_config(config_path)
    completed_actions = []

    for hpc_island_id, island_config in mappings.items():
        available_shapes = available_by_hpc_island.get(hpc_island_id, {})
        cluster = island_config["cluster"]
        cluster_nodes = get_nodes_by_cluster(cluster)

        for shape, shape_config in island_config["shapes"].items():
            try:
                count = int(available_shapes.get(shape, 0) or 0)
            except (TypeError, ValueError):
                logger.error(
                    "Invalid available host count for shape %s in HPC island %s",
                    shape,
                    hpc_island_id,
                )
                continue
            if count <= 0:
                continue

            matching_nodes = _matching_cluster_nodes(cluster_nodes, shape, hpc_island_id)
            if not matching_nodes:
                logger.error(
                    "Refusing to add %d %s node(s) to cluster %s: no configured "
                    "node of that shape exists in HPC island %s",
                    count,
                    shape,
                    cluster,
                    hpc_island_id,
                )
                continue

            if _is_gb_shape(shape):
                _auto_add_gb_memory_fabrics(
                    matching_nodes,
                    shape,
                    shape_config,
                    hpc_island_id,
                    cluster,
                    completed_actions,
                )
                continue

            compartment_ids = {
                node.compartment_id
                for node in matching_nodes
                if getattr(node, "compartment_id", None)
            }
            if len(compartment_ids) != 1:
                logger.error(
                    "Refusing to add nodes to cluster %s: expected one compartment, found %d: %s",
                    cluster,
                    len(compartment_ids),
                    sorted(compartment_ids),
                )
                continue

            logger.info(
                "Adding %d available %s node(s) from HPC island %s to cluster %s",
                count,
                shape,
                hpc_island_id,
                cluster,
            )
            try:
                run_add(
                    matching_nodes,
                    count,
                    [],
                    cluster,
                    next(iter(compartment_ids)),
                )
            except SystemExit as exc:
                logger.error("Auto-add failed for cluster %s: %s", cluster, exc)
                continue
            except Exception as exc:
                logger.exception("Auto-add failed for cluster %s: %s", cluster, exc)
                continue

            completed_actions.append({
                "type": "cluster",
                "hpc_island_id": hpc_island_id,
                "shape": shape,
                "cluster": cluster,
                "count": count,
            })

    return completed_actions
