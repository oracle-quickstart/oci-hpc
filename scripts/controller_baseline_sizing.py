#!/usr/bin/env python3
"""Estimate a Slurm controller CPU and memory baseline from service samples."""

import argparse
import csv
import json
import math
import sys
from collections import defaultdict

GIB = 1024**3
REQUIRED_COLUMNS = {
    "timestamp_iso",
    "service",
    "cpu_sec_per_sec",
    "mem_bytes",
}


class SizingError(RuntimeError):
    """Raised when the input cannot produce a reliable estimate."""


def positive_number(value):
    number = float(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def nonnegative_number(value):
    number = float(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def positive_integer(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def percentile(values, quantile):
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def read_samples(path):
    samples = defaultdict(lambda: {"cpu": 0.0, "memory": 0, "services": set()})
    all_services = set()

    try:
        stream = (
            sys.stdin
            if path == "-"
            else open(path, encoding="utf-8", newline="")
        )
        with stream:
            reader = csv.DictReader(stream)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise SizingError(
                    "input is missing columns: " + ", ".join(sorted(missing))
                )
            for line_number, row in enumerate(reader, start=2):
                timestamp = row["timestamp_iso"].strip()
                service = row["service"].strip()
                if not timestamp or not service:
                    raise SizingError(
                        f"empty timestamp or service on line {line_number}"
                    )
                try:
                    cpu = float(row["cpu_sec_per_sec"])
                    memory = int(row["mem_bytes"])
                except ValueError as exc:
                    raise SizingError(
                        f"invalid CPU or memory value on line {line_number}"
                    ) from exc
                if cpu < 0 or memory < 0:
                    raise SizingError(
                        f"negative CPU or memory value on line {line_number}"
                    )
                if service in samples[timestamp]["services"]:
                    raise SizingError(
                        f"duplicate service {service!r} at {timestamp}"
                    )
                samples[timestamp]["cpu"] += cpu
                samples[timestamp]["memory"] += memory
                samples[timestamp]["services"].add(service)
                all_services.add(service)
    except OSError as exc:
        raise SizingError(f"could not read {path}: {exc}") from exc

    if not samples:
        raise SizingError("input contains no samples")

    incomplete = [
        timestamp
        for timestamp, sample in samples.items()
        if sample["services"] != all_services
    ]
    if incomplete:
        raise SizingError(
            f"{len(incomplete)} timestamps do not contain every sampled service"
        )

    return samples, sorted(all_services)


def calculate(args, samples, services):
    p99_cpu_vcpus = percentile(
        [sample["cpu"] for sample in samples.values()], 0.99
    )
    p99_memory_gib = percentile(
        [sample["memory"] for sample in samples.values()], 0.99
    ) / GIB

    calculated_ocpus = args.cpu_reserve_ocpus + (
        p99_cpu_vcpus / args.vcpus_per_ocpu
    ) * (1 + args.cpu_buffer_percent / 100)
    recommended_ocpus = max(args.minimum_ocpus, math.ceil(calculated_ocpus))

    calculated_memory = args.memory_reserve_gib + p99_memory_gib * (
        1 + args.memory_buffer_percent / 100
    )
    recommended_memory = max(
        args.minimum_memory_gib,
        math.ceil(calculated_memory / args.memory_round_gib)
        * args.memory_round_gib,
    )

    return {
        "observed_nodes": args.observed_nodes,
        "sample_count": len(samples),
        "services": services,
        "p99": {
            "logical_cpus": p99_cpu_vcpus,
            "memory_gib": p99_memory_gib,
        },
        "recommended_controller_baseline": {
            "ocpus": recommended_ocpus,
            "memory_gib": recommended_memory,
        },
        "assumptions": {
            "vcpus_per_ocpu": args.vcpus_per_ocpu,
            "cpu_buffer_percent": args.cpu_buffer_percent,
            "memory_buffer_percent": args.memory_buffer_percent,
            "cpu_reserve_ocpus": args.cpu_reserve_ocpus,
            "memory_reserve_gib": args.memory_reserve_gib,
            "minimum_ocpus": args.minimum_ocpus,
            "minimum_memory_gib": args.minimum_memory_gib,
            "memory_round_gib": args.memory_round_gib,
        },
    }


def print_text(result):
    if result["observed_nodes"] is not None:
        print(f"Observed compute nodes: {result['observed_nodes']}")
    print("Services: " + ", ".join(result["services"]))
    print(f"Complete samples: {result['sample_count']}")
    print(
        "Observed combined p99: "
        f"{result['p99']['logical_cpus']:.4f} logical CPUs, "
        f"{result['p99']['memory_gib']:.2f} GiB memory"
    )
    recommendation = result["recommended_controller_baseline"]
    print(
        "Estimated controller baseline: "
        f"{recommendation['ocpus']} OCPUs / "
        f"{recommendation['memory_gib']:.0f} GiB memory"
    )
    assumptions = result["assumptions"]
    print(
        "CPU formula: reserve + p99 logical CPUs / vCPUs per OCPU x buffer = "
        f"{assumptions['cpu_reserve_ocpus']:g} + p99 / "
        f"{assumptions['vcpus_per_ocpu']:g} x "
        f"{1 + assumptions['cpu_buffer_percent'] / 100:.2f}; "
        f"minimum {assumptions['minimum_ocpus']:g} OCPUs"
    )
    print(
        "Memory formula: reserve + p99 memory x buffer = "
        f"{assumptions['memory_reserve_gib']:g} GiB + p99 x "
        f"{1 + assumptions['memory_buffer_percent'] / 100:.2f}; "
        f"round to {assumptions['memory_round_gib']:g} GiB, "
        f"minimum {assumptions['minimum_memory_gib']:g} GiB"
    )
    print(
        "This is a starting point for the sampled services; validate whole-host "
        "usage and representative peak workload."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Estimate a Slurm controller baseline from CSV output produced by "
            "service_usage_stats.sh."
        )
    )
    parser.add_argument(
        "--input", required=True, help="input CSV path, or - for stdin"
    )
    parser.add_argument("--observed-nodes", type=positive_integer)
    parser.add_argument("--vcpus-per-ocpu", type=positive_number, default=2)
    parser.add_argument(
        "--cpu-buffer-percent", type=nonnegative_number, default=50
    )
    parser.add_argument(
        "--memory-buffer-percent", type=nonnegative_number, default=25
    )
    parser.add_argument(
        "--cpu-reserve-ocpus", type=nonnegative_number, default=1
    )
    parser.add_argument(
        "--memory-reserve-gib", type=nonnegative_number, default=4
    )
    parser.add_argument("--minimum-ocpus", type=positive_integer, default=4)
    parser.add_argument("--minimum-memory-gib", type=positive_integer, default=16)
    parser.add_argument("--memory-round-gib", type=positive_integer, default=4)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        samples, services = read_samples(args.input)
        result = calculate(args, samples, services)
    except SizingError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
