#!/usr/bin/env python3
"""Estimate monitoring CPU, memory, and disk from Prometheus and Grafana."""

import argparse
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

GIB = 1024**3
MEMORY_HEADROOM = 1.25
CPU_HEADROOM = 1.50
DEDICATED_BASE_MEMORY_GIB = 4
DEDICATED_BASE_OCPU = 1
MINIMUM_DEDICATED_MEMORY_GIB = 8
MINIMUM_OCPU = 4
LARGE_CLUSTER_NODE_THRESHOLD = 128
LARGE_CLUSTER_MINIMUM_OCPU = 8
REQUEST_TIMEOUT = 10
GRAFANA_SAMPLE_SECONDS = 5
SECONDS_PER_DAY = 86400
BYTES_PER_SAMPLE = 2
DISK_HEADROOM = 1.25
DISK_STEP_GIB = 50
CONTROLLER_BASE_OCPU = 4
CONTROLLER_BASE_MEMORY_GIB = 16
CONTROLLER_BASE_DISK_GIB = 100
DURATION_RE = re.compile(r"^[1-9][0-9]*(?:ms|s|m|h|d|w|y)$")


class SizingError(RuntimeError):
    """Raised when a required metric cannot be collected."""


def read_url(url):
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            return response.read().decode("utf-8")
    except (OSError, UnicodeDecodeError, urllib.error.URLError) as exc:
        raise SizingError(f"request failed for {url}: {exc}") from exc


def prometheus_query(base_url, query):
    url = f"{base_url.rstrip('/')}/api/v1/query?" + urllib.parse.urlencode(
        {"query": query}
    )
    try:
        payload = json.loads(read_url(url))
        result = payload["data"]["result"]
        if payload.get("status") != "success" or not result:
            raise SizingError(f"Prometheus returned no data for: {query}")
        return sum(float(item["value"][1]) for item in result)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SizingError(f"unexpected Prometheus response for: {query}") from exc


def metric_value(metrics_text, metric_name):
    pattern = re.compile(
        rf"^{re.escape(metric_name)}(?:\{{[^}}]*\}})?\s+([^\s]+)(?:\s+\d+)?$"
    )
    values = []
    for line in metrics_text.splitlines():
        match = pattern.match(line)
        if match:
            try:
                values.append(float(match.group(1)))
            except ValueError as exc:
                raise SizingError(
                    f"invalid {metric_name} value from Grafana"
                ) from exc
    if not values:
        raise SizingError(f"Grafana /metrics did not expose {metric_name}")
    return sum(values)


def collect_grafana_live(url):
    first = read_url(url)
    first_cpu = metric_value(first, "process_cpu_seconds_total")
    started = time.monotonic()
    time.sleep(GRAFANA_SAMPLE_SECONDS)
    second = read_url(url)
    elapsed = time.monotonic() - started
    second_cpu = metric_value(second, "process_cpu_seconds_total")
    if second_cpu < first_cpu:
        raise SizingError("Grafana restarted during the CPU sample; run again")
    return {
        "memory_bytes": max(
            metric_value(first, "process_resident_memory_bytes"),
            metric_value(second, "process_resident_memory_bytes"),
        ),
        "cpu_cores": (second_cpu - first_cpu) / elapsed,
        "method": f"live {elapsed:.1f}s sample from {url}",
    }


def round_up(value, step=1):
    return int(math.ceil(value / step) * step)


def calculate(args, observed):
    current_nodes = observed["current_nodes"]
    observed_memory_coefficient = observed["combined_memory_gib"] / current_nodes
    observed_ocpu_coefficient = (
        observed["combined_cpu_cores"] / args.vcpus_per_ocpu / current_nodes
    )
    memory_coefficient = observed_memory_coefficient * MEMORY_HEADROOM
    ocpu_coefficient = observed_ocpu_coefficient * CPU_HEADROOM
    samples_coefficient = observed["samples_per_second"] / current_nodes

    retention_seconds = observed["retention_seconds"]
    if args.retention_days is not None:
        retention_seconds = args.retention_days * SECONDS_PER_DAY
    if retention_seconds <= 0:
        raise SizingError(
            "Prometheus reported no time retention; pass --retention-days"
        )

    projected_memory = memory_coefficient * args.target_nodes
    projected_ocpu = ocpu_coefficient * args.target_nodes
    projected_samples = samples_coefficient * args.target_nodes
    minimum_ocpu = (
        LARGE_CLUSTER_MINIMUM_OCPU
        if args.target_nodes >= LARGE_CLUSTER_NODE_THRESHOLD
        else MINIMUM_OCPU
    )
    raw_tsdb_gib = (
        projected_samples * retention_seconds * BYTES_PER_SAMPLE / GIB
    )
    prometheus_disk = math.ceil(raw_tsdb_gib * DISK_HEADROOM)
    boot_volume = round_up(
        prometheus_disk + args.system_disk_gib,
        DISK_STEP_GIB,
    )
    dedicated_memory = max(
        MINIMUM_DEDICATED_MEMORY_GIB,
        round_up(
            DEDICATED_BASE_MEMORY_GIB + projected_memory,
            4,
        ),
    )
    dedicated_ocpu = max(
        minimum_ocpu,
        math.ceil(DEDICATED_BASE_OCPU + projected_ocpu),
    )
    controller_memory = max(2, math.ceil(projected_memory))
    controller_ocpu = max(minimum_ocpu, math.ceil(projected_ocpu))
    controller_boot_volume = round_up(
        CONTROLLER_BASE_DISK_GIB + prometheus_disk,
        DISK_STEP_GIB,
    )

    return {
        "environment": args.environment,
        "observed": observed,
        "coefficients": {
            "observed_memory_gib_per_node": observed_memory_coefficient,
            "observed_ocpu_per_node": observed_ocpu_coefficient,
            "memory_gib_per_node": memory_coefficient,
            "ocpu_per_node": ocpu_coefficient,
            "samples_per_second_per_node": samples_coefficient,
        },
        "target_nodes": args.target_nodes,
        "dedicated_monitoring_node": {
            "memory_gib": dedicated_memory,
            "ocpu": dedicated_ocpu,
            "boot_volume_gib": boot_volume,
        },
        "controller_monitoring_addon": {
            "memory_gib": controller_memory,
            "ocpu": controller_ocpu,
            "prometheus_disk_gib": prometheus_disk,
            "boot_volume_gib": controller_boot_volume
            - CONTROLLER_BASE_DISK_GIB,
        },
        "controller_baseline": {
            "memory_gib": CONTROLLER_BASE_MEMORY_GIB,
            "ocpu": CONTROLLER_BASE_OCPU,
            "boot_volume_gib": CONTROLLER_BASE_DISK_GIB,
        },
        "controller_with_monitoring": {
            "memory_gib": CONTROLLER_BASE_MEMORY_GIB + controller_memory,
            "ocpu": CONTROLLER_BASE_OCPU + controller_ocpu,
            "boot_volume_gib": controller_boot_volume,
        },
        "assumptions": {
            "memory_headroom": MEMORY_HEADROOM,
            "cpu_headroom": CPU_HEADROOM,
            "vcpus_per_ocpu": args.vcpus_per_ocpu,
            "dedicated_base_memory_gib": DEDICATED_BASE_MEMORY_GIB,
            "dedicated_base_ocpu": DEDICATED_BASE_OCPU,
            "retention_days": retention_seconds / SECONDS_PER_DAY,
            "bytes_per_sample": BYTES_PER_SAMPLE,
            "disk_headroom": DISK_HEADROOM,
            "system_disk_gib": args.system_disk_gib,
            "disk_rounding_gib": DISK_STEP_GIB,
            "large_cluster_node_threshold": LARGE_CLUSTER_NODE_THRESHOLD,
            "large_cluster_minimum_ocpu": LARGE_CLUSTER_MINIMUM_OCPU,
        },
    }


def collect(args):
    current_nodes = args.current_nodes
    if current_nodes is None:
        current_nodes = round(
            prometheus_query(
                args.prometheus_url,
                'count(count by (hostname) (up{role="compute",instance=~".*:9100$"}))',
            )
        )
    if current_nodes < 1:
        raise SizingError("current compute-node count must be at least 1")

    prometheus_memory = prometheus_query(
        args.prometheus_url,
        "quantile_over_time(0.99, "
        f'process_resident_memory_bytes{{job="prometheus-self"}}[{args.window}])',
    )
    prometheus_cpu = prometheus_query(
        args.prometheus_url,
        "quantile_over_time(0.99, "
        'rate(process_cpu_seconds_total{job="prometheus-self"}[5m])'
        f"[{args.window}:5m])",
    )
    grafana = collect_grafana_live(args.grafana_url)

    return {
        "window": args.window,
        "current_nodes": current_nodes,
        "prometheus_memory_gib": prometheus_memory / GIB,
        "prometheus_cpu_cores": prometheus_cpu,
        "grafana_memory_gib": grafana["memory_bytes"] / GIB,
        "grafana_cpu_cores": grafana["cpu_cores"],
        "grafana_method": grafana["method"],
        "combined_memory_gib": (prometheus_memory + grafana["memory_bytes"]) / GIB,
        "combined_cpu_cores": prometheus_cpu + grafana["cpu_cores"],
        "storage_blocks_gib": prometheus_query(
            args.prometheus_url,
            "prometheus_tsdb_storage_blocks_bytes",
        )
        / GIB,
        "storage_head_gib": prometheus_query(
            args.prometheus_url,
            "prometheus_tsdb_head_chunks_storage_size_bytes",
        )
        / GIB,
        "retention_seconds": prometheus_query(
            args.prometheus_url,
            "prometheus_tsdb_retention_limit_seconds",
        ),
        "active_series": round(
            prometheus_query(
                args.prometheus_url,
                "prometheus_tsdb_head_series",
            )
        ),
        "samples_per_second": prometheus_query(
            args.prometheus_url,
            "avg_over_time("
            "rate(prometheus_tsdb_head_samples_appended_total[5m])"
            f"[{args.window}:5m])",
        ),
    }


def print_text(result):
    observed = result["observed"]
    coefficient = result["coefficients"]
    dedicated = result["dedicated_monitoring_node"]
    controller = result["controller_monitoring_addon"]
    controller_baseline = result["controller_baseline"]
    controller_total = result["controller_with_monitoring"]
    print(f"Environment: {result['environment']}")
    print(
        "Controller baseline without monitoring: "
        f"{controller_baseline['ocpu']} OCPUs / "
        f"{controller_baseline['memory_gib']} GiB / "
        f"{controller_baseline['boot_volume_gib']} GiB boot"
    )
    print(
        f"Observed nodes: {observed['current_nodes']} over {observed['window']}; "
        f"{observed['active_series']} active series; "
        f"{observed['samples_per_second']:.1f} samples/s"
    )
    print(
        "Prometheus + Grafana: "
        f"{observed['combined_memory_gib']:.2f} GiB, "
        f"{observed['combined_cpu_cores']:.3f} CPU cores"
    )
    print(f"Grafana measurement: {observed['grafana_method']}")
    print(
        "Buffered coefficients: "
        f"{coefficient['memory_gib_per_node']:.4f} GiB/node, "
        f"{coefficient['ocpu_per_node']:.6f} OCPU/node"
    )
    print(
        f"For {result['target_nodes']} nodes: dedicated = "
        f"{dedicated['ocpu']} OCPUs / {dedicated['memory_gib']} GiB / "
        f"{dedicated['boot_volume_gib']} GiB boot"
    )
    print(
        "Controller monitoring add-on: "
        f"+{controller['ocpu']} OCPUs / +{controller['memory_gib']} GiB / "
        f"+{controller['boot_volume_gib']} GiB boot"
    )
    print(
        "Controller total with monitoring: "
        f"{controller_total['ocpu']} OCPUs / "
        f"{controller_total['memory_gib']} GiB / "
        f"{controller_total['boot_volume_gib']} GiB boot"
    )
    assumptions = result["assumptions"]
    current_tsdb = observed["storage_blocks_gib"] + observed["storage_head_gib"]
    print(
        "Current Prometheus blocks + head: "
        f"{current_tsdb:.1f} GiB (WAL excluded)"
    )
    print(
        "Disk inputs: "
        f"{coefficient['samples_per_second_per_node']:.1f} samples/s/node, "
        f"{assumptions['retention_days']:.1f} days retention, "
        f"{assumptions['bytes_per_sample']} bytes/sample"
    )
    print(
        f"Disk for {result['target_nodes']} nodes: dedicated boot volume = "
        f"{dedicated['boot_volume_gib']} GiB; Prometheus requires "
        f"{controller['prometheus_disk_gib']} GiB"
    )
    print(
        "Formula: memory = 4 GiB base + buffered memory coefficient x nodes; "
        "OCPU = 1 base + buffered OCPU coefficient x nodes; "
        "minimum 4 below 128 nodes and 8 from 128 nodes"
    )
    print(
        "Disk formula: projected samples/s x retention x 2 bytes/sample, "
        f"+25%; dedicated boot volume adds {assumptions['system_disk_gib']} "
        f"GiB and rounds to {assumptions['disk_rounding_gib']} GiB"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Estimate Prometheus and Grafana monitoring-node resources."
    )
    parser.add_argument("--target-nodes", type=int, required=True)
    parser.add_argument("--current-nodes", type=int)
    parser.add_argument("--environment", default="local")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--grafana-url", default="http://localhost:3000/metrics")
    parser.add_argument("--window", default="7d")
    parser.add_argument("--vcpus-per-ocpu", type=float, default=2.0)
    parser.add_argument(
        "--retention-days",
        type=float,
        help="Override the retention reported by Prometheus",
    )
    parser.add_argument(
        "--system-disk-gib",
        type=int,
        default=50,
        help="System reserve for a dedicated monitoring node",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    if args.target_nodes < 1:
        parser.error("--target-nodes must be at least 1")
    if args.current_nodes is not None and args.current_nodes < 1:
        parser.error("--current-nodes must be at least 1")
    if not DURATION_RE.fullmatch(args.window):
        parser.error("--window must be a Prometheus duration such as 24h or 7d")
    if args.vcpus_per_ocpu <= 0:
        parser.error("--vcpus-per-ocpu must be greater than 0")
    if args.retention_days is not None and args.retention_days <= 0:
        parser.error("--retention-days must be greater than 0")
    if args.system_disk_gib < 0:
        parser.error("--system-disk-gib cannot be negative")
    return args


def main():
    args = parse_args()
    try:
        result = calculate(args, collect(args))
    except SizingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
