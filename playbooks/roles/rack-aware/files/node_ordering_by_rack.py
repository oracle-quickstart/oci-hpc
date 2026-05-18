#!/usr/bin/env -S /config/bin/uv_wrapper.sh run --script
#
# /// script
# dependencies = ["ClusterShell"]
# ///
from __future__ import annotations

import json
import argparse
import subprocess
import re
import doctest
from collections import defaultdict
import importlib
from typing import TYPE_CHECKING, TypeAlias

if TYPE_CHECKING:
    from ClusterShell.NodeSet import NodeSet


IMDS_ENDPOINT = "http://169.254.169.254/opc/v2/host"
ID_SUFFIX_LEN = 8

TOPOLOGY_SWITCH_RE = re.compile(
    r"^SwitchName=(\S+)\s+Level=(\d+)\s+.*?Nodes=([^ ]*)(?:\s+Switches=(.*))?$"
)
TOPOLOGY_BLOCK_RE = re.compile(
    r"^(BlockName|AggregatedBlock)=(\S+)\s+BlockIndex=\d+\s+Nodes=([^ ]*)\s+BlockSize=(\d+)$"
)
NULL_TOPOLOGY_FIELD_VALUES = {"", "(null)", "None", "none"}

TopologyParents: TypeAlias = dict[str, str]
TopologyLevels: TypeAlias = dict[str, int]
TopologyLeaves: TypeAlias = dict[str, "NodeSet"]
TopologyData: TypeAlias = tuple[TopologyParents, TopologyLevels, TopologyLeaves]

################################################################
# Dynamic loading of ClusterShell Module:
# The ClusterShell library makes parsing nodeset names easier and has many extremely useful
# features.
# While the library is mandatory we make loading dynamic and catch the case when the module is not
# found to print a friendly error message


_ClusterShell_NodeSet = None
_ClusterShell_Task = None

def get_nodeset_class():
    global _ClusterShell_NodeSet
    if _ClusterShell_NodeSet is None:
        try:
            _ClusterShell_NodeSet = importlib.import_module("ClusterShell.NodeSet").NodeSet
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "ClusterShell is required for compact --show-nodelist output. "
                "Install it in the runtime environment (use uv!) before running this script."
            ) from exc
    return _ClusterShell_NodeSet


def get_task_self():
    global _ClusterShell_Task
    if _ClusterShell_Task is None:
        try:
            _ClusterShell_Task = importlib.import_module("ClusterShell.Task").task_self
        except ModuleNotFoundError as exc:
            raise SystemExit(
                "ClusterShell is required for IMDS topology discovery. "
                "Install it in the runtime environment (use uv!) before running this script."
            ) from exc
    return _ClusterShell_Task
################################################################


def parse_nodeset(expr: str) -> "NodeSet":
    """convert string into a ClusterShell.NodeSet

    Returns an instance of ClusterShell.NodeSet.NodeSet. NodeSet is returned empty if
    `expr` represents an empty Nodelist
    """
    NodeSet = get_nodeset_class()
    if expr in NULL_TOPOLOGY_FIELD_VALUES:
        return NodeSet()
    return NodeSet(expr)


def coerce_nodeset(nodes: object) -> "NodeSet":
    """Normalize ClusterShell node selectors into a NodeSet instance.

    >>> str(coerce_nodeset("gpu-[1-2]"))
    'gpu-[1-2]'
    >>> str(coerce_nodeset(["gpu-1", "gpu-2"]))
    'gpu-[1-2]'
    """
    NodeSet = get_nodeset_class()
    if isinstance(nodes, NodeSet):
        return nodes
    if isinstance(nodes, str):
        return parse_nodeset(nodes)
    try:
        return NodeSet.fromlist([str(node) for node in nodes])
    except TypeError:
        return parse_nodeset(str(nodes))


def prune_topology_to_allocated_nodes(
    parents: TopologyParents,
    levels: TopologyLevels,
    level0_nodesets: TopologyLeaves,
    allocated_nodes: "NodeSet",
) -> TopologyData:
    """Prunes full cluster topology to nodes from job allocation.

    Uses set-like operations only:

    >>> parents = {"rack:a": "block:1", "rack:b": "block:1", "rack:c": "block:2"}
    >>> levels = {"block:1": 1, "block:2": 1, "rack:a": 0, "rack:b": 0, "rack:c": 0}
    >>> leaves = {"rack:a": {"gpu-1", "gpu-2"}, "rack:b": {"gpu-3"}, "rack:c": {"gpu-9"}}
    >>> prune_topology_to_allocated_nodes(parents, levels, leaves, {"gpu-2", "gpu-3"})
    ({'rack:a': 'block:1', 'rack:b': 'block:1'}, {'block:1': 1, 'rack:a': 0, 'rack:b': 0}, {'rack:a': {'gpu-2'}, 'rack:b': {'gpu-3'}})
    """
    pruned_leaves: TopologyLeaves = {}
    kept_names: set[str] = set()

    for name, nodes in level0_nodesets.items():
        scoped_nodes = nodes & allocated_nodes
        if not scoped_nodes:
            continue

        pruned_leaves[name] = scoped_nodes

        current = name
        kept_names.add(current)
        while current in parents:
            current = parents[current]
            kept_names.add(current)

    pruned_parents = {
        child: ancestor
        for child, ancestor in parents.items()
        if child in kept_names and ancestor in kept_names
    }
    pruned_levels = {
        name: level
        for name, level in levels.items()
        if name in kept_names
    }
    return pruned_parents, pruned_levels, pruned_leaves


def register_block_hierarchy(
    name: str,
    nodes_expr: str,
    parents: TopologyParents,
    levels: TopologyLevels,
    level0_nodesets: TopologyLeaves,
) -> None:
    """Helper function for building cluster topology"""
    parts = [part for part in name.split(":") if part]
    if not parts:
        return

    path_names = [":".join(parts[:index]) for index in range(1, len(parts) + 1)]
    max_level = len(path_names) - 1

    for index, path_name in enumerate(path_names):
        levels[path_name] = max_level - index
        if index > 0:
            parents[path_name] = path_names[index - 1]

    level0_nodesets[path_names[-1]] = parse_nodeset(nodes_expr)


def query_scontrol_topology() -> str:
    """Retrieves cluster topology using `scontrol show topology`."""
    try:
        result = subprocess.run(
            ["scontrol", "show", "topology"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except subprocess.CalledProcessError as cpe:
        print(f"scontrol show topology exited with {cpe.returncode}")
        print("stderr follows:")
        print(cpe.stderr if cpe.stderr is not None else "")
        raise
    return result.stdout

def parse_scontrol_topology(allocated_nodes: "NodeSet") -> TopologyData:
    """Builds cluster node topology using data obtained from `scontrol show topology`."""
    parents: TopologyParents = {}
    levels: TopologyLevels = {}
    level0_nodesets: TopologyLeaves = {}
    saw_parseable_line = False

    for raw_line in query_scontrol_topology().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if block_match := TOPOLOGY_BLOCK_RE.match(line):
            saw_parseable_line = True
            kind, name, nodes_expr, _ = block_match.groups()
            if kind != "BlockName":
                continue
            register_block_hierarchy(name, nodes_expr, parents, levels, level0_nodesets)

        elif match := TOPOLOGY_SWITCH_RE.match(line):
            saw_parseable_line = True
            name, level_text, nodes_expr, switches_expr = match.groups()
            level = int(level_text)
            levels[name] = level

            if level == 0:
                level0_nodesets[name] = parse_nodeset(nodes_expr)

            if switches_expr and switches_expr not in NULL_TOPOLOGY_FIELD_VALUES:
                for child in (item.strip() for item in switches_expr.split(",")):
                    if not child or child in NULL_TOPOLOGY_FIELD_VALUES:
                        continue
                    parents[child] = name

    if not saw_parseable_line:
        raise RuntimeError("scontrol show topology returned no parseable topology entries")

    topology = prune_topology_to_allocated_nodes(
        parents,
        levels,
        level0_nodesets,
        allocated_nodes,
    )
    if not topology[2]:
        raise RuntimeError("scontrol topology did not contain any level-0 leaves for allocated hosts")

    return topology


def rack_key_from_imds_json(doc: dict) -> str | None:
    """Parse returned JSON object from IMDS for rack ID.

    >>> rack_key_from_imds_json({"rdmaTopologyData": {"customerLocalBlock": "abcd1234"}})
    'abcd1234'
    >>> rack_key_from_imds_json({"rdmaTopologyData": {"customerLocalBlock": "None"}, "rackId": "rack0009"})
    'rack0009'
    >>> rack_key_from_imds_json({"rdmaTopologyData": {"customerLocalBlock": "none"}, "rackId": None}) is None
    True
    """
    rdma_topology = doc.get("rdmaTopologyData", {})
    rack = rdma_topology.get("customerLocalBlock")
    if rack in NULL_TOPOLOGY_FIELD_VALUES or not rack:
        rack = doc.get("rackId")
    if rack in NULL_TOPOLOGY_FIELD_VALUES or not rack:
        return None
    return str(rack)[-ID_SUFFIX_LEN:]


def block_key_from_imds_json(doc: dict) -> str | None:
    """Parse returned JSON object from IMDS for network block ID.

    >>> block_key_from_imds_json({"rdmaTopologyData": {"customerNetworkBlock": "block123"}})
    'block123'
    >>> block_key_from_imds_json({"rdmaTopologyData": {"customerNetworkBlock": "(null)"}, "networkBlockId": "net98765"})
    'net98765'
    >>> block_key_from_imds_json({"networkBlockId": "None"}) is None
    True
    """
    rdma_topology = doc.get("rdmaTopologyData", {})
    block = rdma_topology.get("customerNetworkBlock")
    if block in NULL_TOPOLOGY_FIELD_VALUES or not block:
        block = doc.get("networkBlockId")
    if block in NULL_TOPOLOGY_FIELD_VALUES or not block:
        return None
    return str(block)[-ID_SUFFIX_LEN:]


def get_topology_from_imds(nodes: "NodeSet") -> TopologyData:
    """Determines cluster topology using rack and network block information retrieved by querying
    IMDS endpoint from all allocated nodes.

    This method is intended as a fallback if `scontrol show topology` is not available.
    """
    parents: TopologyParents = {}
    levels: TopologyLevels = {}
    level0_nodesets: dict[str, "NodeSet"] = defaultdict(get_nodeset_class())

    cmd = (
        "curl -H 'Authorization: Bearer Oracle' "
        f"-fsS -L '{IMDS_ENDPOINT}'"
    )
    task = get_task_self()()
    task.run(cmd, nodes=nodes)
    saw_valid_imds_data = False

    for buf, out_nodes in task.iter_buffers():
        s = bytes(buf).decode(errors="replace").strip()
        out_nodeset = coerce_nodeset(out_nodes)
        try:
            doc = json.loads(s)
        except json.JSONDecodeError:
            print(f"WARN: IMDS returned an invalid JSON for {out_nodeset}.")
            print(s)
            continue

        rk = rack_key_from_imds_json(doc)
        bk = block_key_from_imds_json(doc)
        if not rk or not bk:
            print(f"WARN: no block or rack reported for {out_nodeset}.")
            print(s)
            continue

        saw_valid_imds_data = True
        block_name = f"block:{bk}"
        rack_name = f"{block_name}:rack:{rk}"
        levels[block_name] = 1
        levels[rack_name] = 0
        parents[rack_name] = block_name
        level0_nodesets[rack_name] |= out_nodeset

    for node, err in task.iter_errors():
        msg = err.decode(errors="replace").strip()
        if msg:
            print(f"WARN: {node} stderr: {msg}")

    if not saw_valid_imds_data:
        raise RuntimeError("IMDS queries returned no usable topology metadata")

    return (parents, levels, dict(level0_nodesets))


def topology_path(name: str, parents: TopologyParents) -> tuple[str, ...]:
    """Determines the topology path top to bottom for any given, block, switch, or rack.

    Traverse the TopologyParents dict for a given node in the toplogy tree.

    >>> topology_path("rack:a", {"rack:a": "block:1", "block:1": "root"})
    ('root', 'block:1', 'rack:a')
    >>> topology_path("root", {})
    ('root',)
    """
    path = [name]
    current = name
    while current in parents:
        current = parents[current]
        path.append(current)
    path.reverse()
    return tuple(path)


def order_hosts_from_topology(topology: TopologyData) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Orders allocated hosts according to their topology preserving closeness in topology.

    Siblings in a rack are listed closest, nodes witin a block (or Level>0 switch) are listed
    together)

    >>> topology = (
    ...     {"block:1:rack:b": "block:1", "block:1:rack:a": "block:1", "block:2:rack:c": "block:2"},
    ...     {"block:1": 1, "block:2": 1, "block:1:rack:a": 0, "block:1:rack:b": 0, "block:2:rack:c": 0},
    ...     {"block:1:rack:b": ["gpu-3"], "block:2:rack:c": ["gpu-9"], "block:1:rack:a": ["gpu-1", "gpu-2"]},
    ... )
    >>> order_hosts_from_topology(topology)
    (['gpu-1', 'gpu-2', 'gpu-3', 'gpu-9'], [('block:1:rack:a', ['gpu-1', 'gpu-2']), ('block:1:rack:b', ['gpu-3']), ('block:2:rack:c', ['gpu-9'])])
    """
    parents, _, level0_nodesets = topology
    ordered_leaf_names = sorted(
        level0_nodesets,
        key=lambda name: topology_path(name, parents),
    )

    ordered_hosts: list[str] = []
    ordered_groups: list[tuple[str, list[str]]] = []

    for leaf_name in ordered_leaf_names:
        leaf_hosts = list(level0_nodesets[leaf_name])
        ordered_hosts.extend(leaf_hosts)
        ordered_groups.append((leaf_name, leaf_hosts))

    return ordered_hosts, ordered_groups


def write_ordered_hostfile(ordered_hosts, hostfile, ngpus=1, srun=False):
    with open(hostfile, "w") as fhandler:
        for h in ordered_hosts:
            if srun:
                for _ in range(ngpus):
                    fhandler.write(h+"\n")
            else:
                fhandler.write(h+"\n")


def write_ordered_rankfile(ordered_hosts, rankfile, ngpus):
    with open(rankfile, "w") as fhandler:
        for index,h in enumerate(ordered_hosts):
            for gpu_index in range(ngpus):
                fhandler.write(f"rank {index*ngpus+gpu_index}={h} slot={gpu_index}\n")


def write_ordered_hostlist(ordered_hosts, hostlist_file):
    with open(hostlist_file, "w") as fhandler:
        fhandler.write(",".join(ordered_hosts))


def setup_args():
    parser = argparse.ArgumentParser(description='Script to order hostnames for optimal performance based on rack Id')
    parser.add_argument('--input_file', help='Path of the input file which has host names. One hostname on each line in the file')
    parser.add_argument('--gpus', type=int, default=8, help='Number of GPUs per node')
    parser.add_argument('--imds', action='store_true', help='Skip Slurm topology parsing and use IMDS topology discovery directly')
    parser.add_argument('--selftest', action='store_true', help='Run embedded doctest sanity checks and exit')
    return parser.parse_args()

def main():
    args = setup_args()

    if args.selftest:
        failures, _ = doctest.testmod(optionflags=doctest.ELLIPSIS)
        raise SystemExit(1 if failures else 0)

    if not args.input_file:
        raise SystemExit("--input_file is required unless --selftest is used")

    with open(args.input_file, 'r') as f:
        hosts = f.read().splitlines()
    NodeSet = get_nodeset_class()
    nodes = NodeSet.fromlist(hosts)
    print(f'Ordering following hosts: {nodes}')

    if args.imds:
        topology = get_topology_from_imds(nodes)
        topology_source = "imds"
    else:
        try:
            topology = parse_scontrol_topology(nodes)
            topology_source = "slurm"
        except (subprocess.CalledProcessError, RuntimeError):
            topology = get_topology_from_imds(nodes)
            topology_source = "imds"

    ordered_hosts, ordered_groups = order_hosts_from_topology(topology)
    print(f"Using topology source: {topology_source}")

    with open("node_switch_list", "w") as fhandler:
        for index, (group_name, group_hosts) in enumerate(ordered_groups, start=1):
            print(f"# rack {index} ({group_name})")
            for host in group_hosts:
                fhandler.write(f"Node {host} from topology leaf {group_name}\n")
                print(host)

    write_ordered_hostfile(ordered_hosts, "ordered_hostfile")
    write_ordered_hostfile(ordered_hosts, "ordered_hostfile_system_name_srun", ngpus=args.gpus, srun=True)
    write_ordered_rankfile(ordered_hosts, "ordered_rankfile", args.gpus)
    write_ordered_hostlist(ordered_hosts, "ordered_hostlist")


if __name__ == "__main__":
    main()
