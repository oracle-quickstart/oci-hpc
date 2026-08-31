#!/usr/bin/env python3
"""
Prometheus exporter for Lustre MDT and OST capacity from `lfs df -h`.
"""

from __future__ import annotations

import argparse
import logging
import re
import selectors
import subprocess
import threading
import time

from dataclasses import dataclass
from typing import Iterable

from prometheus_client import Gauge, start_http_server


DEFAULT_INTERVAL_SECONDS = 15 * 60
DEFAULT_PORT = 9718
DEFAULT_ADDR = "0.0.0.0"
DEFAULT_MOUNT_PATH = "/mnt/lfs"
DEFAULT_LFS_COMMAND = "lfs"
DEFAULT_TIMEOUT_SECONDS = 12 * 60

TARGET_RE = re.compile(r"\[(MDT|OST):(\d+)\]$")
SIZE_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)([KMGTPEZY]?)$", re.IGNORECASE)
UNIT_MULTIPLIERS = {
    "": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "P": 1024**5,
    "E": 1024**6,
    "Z": 1024**7,
    "Y": 1024**8,
}


@dataclass(frozen=True)
class LustreTargetUsage:
    uuid: str
    target_type: str
    target_index: str
    mounted_on: str
    bytes_total: float
    bytes_used: float
    bytes_available: float
    used_percent: float

    @property
    def available_percent(self) -> float:
        if self.bytes_total <= 0:
            return 0.0
        return (self.bytes_available / self.bytes_total) * 100.0


@dataclass(frozen=True)
class LustreFilesystemUsage:
    mounted_on: str
    bytes_total: float
    bytes_used: float
    bytes_available: float
    used_percent: float

    @property
    def available_percent(self) -> float:
        if self.bytes_total <= 0:
            return 0.0
        return (self.bytes_available / self.bytes_total) * 100.0


LABELS = ("target_type", "target_index", "uuid", "mounted_on")
FILESYSTEM_LABELS = ("mounted_on",)

BYTES_TOTAL = Gauge(
    "lustre_target_bytes_total",
    "Total bytes reported by lfs df -h for a Lustre MDT or OST.",
    LABELS,
)
BYTES_USED = Gauge(
    "lustre_target_bytes_used",
    "Used bytes reported by lfs df -h for a Lustre MDT or OST.",
    LABELS,
)
BYTES_AVAILABLE = Gauge(
    "lustre_target_bytes_available",
    "Available bytes reported by lfs df -h for a Lustre MDT or OST.",
    LABELS,
)
USED_PERCENT = Gauge(
    "lustre_target_used_percent",
    "Used capacity percentage reported by lfs df -h for a Lustre MDT or OST.",
    LABELS,
)
AVAILABLE_PERCENT = Gauge(
    "lustre_target_available_percent",
    "Available capacity percentage derived from available bytes divided by total bytes.",
    LABELS,
)
FILESYSTEM_BYTES_TOTAL = Gauge(
    "lustre_filesystem_bytes_total",
    "Total bytes reported by lfs df -h for the Lustre filesystem summary.",
    FILESYSTEM_LABELS,
)
FILESYSTEM_BYTES_USED = Gauge(
    "lustre_filesystem_bytes_used",
    "Used bytes reported by lfs df -h for the Lustre filesystem summary.",
    FILESYSTEM_LABELS,
)
FILESYSTEM_BYTES_AVAILABLE = Gauge(
    "lustre_filesystem_bytes_available",
    "Available bytes reported by lfs df -h for the Lustre filesystem summary.",
    FILESYSTEM_LABELS,
)
FILESYSTEM_USED_PERCENT = Gauge(
    "lustre_filesystem_used_percent",
    "Used capacity percentage reported by lfs df -h for the Lustre filesystem summary.",
    FILESYSTEM_LABELS,
)
FILESYSTEM_AVAILABLE_PERCENT = Gauge(
    "lustre_filesystem_available_percent",
    "Available capacity percentage derived from summary available bytes divided by total bytes.",
    FILESYSTEM_LABELS,
)
SCRAPE_SUCCESS = Gauge(
    "lustre_target_scrape_success",
    "Whether the last lfs df collection completed successfully.",
)
SCRAPE_DURATION_SECONDS = Gauge(
    "lustre_target_scrape_duration_seconds",
    "Seconds spent collecting and parsing the last lfs df output.",
)
SCRAPE_LAST_RUN_TIMESTAMP_SECONDS = Gauge(
    "lustre_target_scrape_last_run_timestamp_seconds",
    "Unix timestamp when the last lfs df collection completed.",
)


def parse_size_to_bytes(raw_size: str) -> float:
    match = SIZE_RE.match(raw_size.strip())
    if not match:
        raise ValueError(f"invalid size value: {raw_size}")

    value = float(match.group(1))
    unit = match.group(2).upper()
    return value * UNIT_MULTIPLIERS[unit]


def parse_used_percent(raw_percent: str) -> float:
    if not raw_percent.endswith("%"):
        raise ValueError(f"invalid percentage value: {raw_percent}")
    return float(raw_percent[:-1])


def parse_lfs_df(output: str) -> list[LustreTargetUsage]:
    rows: list[LustreTargetUsage] = []

    for line_number, line in enumerate(output.splitlines(), start=1):
        row = parse_lfs_df_line(line, line_number)
        if row is not None:
            rows.append(row)

    return rows


def parse_lfs_df_summary_line(line: str) -> LustreFilesystemUsage | None:
    stripped = line.strip()
    if not stripped.startswith("filesystem_summary:"):
        return None

    columns = stripped.split()
    if len(columns) != 6:
        logging.debug("Skipping unrecognized filesystem summary line: %s", line)
        return None

    _, total, used, available, used_percent, mounted_on = columns
    return LustreFilesystemUsage(
        mounted_on=mounted_on,
        bytes_total=parse_size_to_bytes(total),
        bytes_used=parse_size_to_bytes(used),
        bytes_available=parse_size_to_bytes(available),
        used_percent=parse_used_percent(used_percent),
    )


def parse_lfs_df_line(line: str, line_number: int | None = None) -> LustreTargetUsage | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("UUID"):
        return None

    columns = stripped.split()
    if len(columns) != 6:
        if line_number is None:
            logging.debug("Skipping unrecognized lfs df line: %s", line)
        else:
            logging.debug("Skipping unrecognized lfs df line %d: %s", line_number, line)
        return None

    uuid, total, used, available, used_percent, mounted_on = columns
    target_match = TARGET_RE.search(mounted_on)
    if not target_match:
        if line_number is None:
            logging.debug("Skipping non-MDT/OST lfs df line: %s", line)
        else:
            logging.debug("Skipping non-MDT/OST lfs df line %d: %s", line_number, line)
        return None

    target_type, target_index = target_match.groups()
    return LustreTargetUsage(
        uuid=uuid,
        target_type=target_type,
        target_index=target_index,
        mounted_on=mounted_on,
        bytes_total=parse_size_to_bytes(total),
        bytes_used=parse_size_to_bytes(used),
        bytes_available=parse_size_to_bytes(available),
        used_percent=parse_used_percent(used_percent),
    )


def collect_lustre_usage(
    lfs_command: str,
    mount_path: str,
    timeout_seconds: int,
) -> list[LustreTargetUsage]:
    command = [lfs_command, "df", "-h", mount_path]
    logging.debug("Running command: %s", " ".join(command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    rows: list[LustreTargetUsage] = []
    filesystem_usage: LustreFilesystemUsage | None = None
    stderr_lines: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    selector = selectors.DefaultSelector()

    assert process.stdout is not None
    assert process.stderr is not None
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")

    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                raise subprocess.TimeoutExpired(command, timeout_seconds)

            events = selector.select(timeout=min(1.0, remaining))
            if not events and process.poll() is not None:
                events = selector.select(timeout=0)

            for key, _ in events:
                line = key.fileobj.readline()
                if not line:
                    selector.unregister(key.fileobj)
                    continue
                line = line.rstrip("\n")
                if key.data == "stdout":
                    logging.debug("Command stdout: %s", line)
                    summary = parse_lfs_df_summary_line(line)
                    if summary is not None:
                        filesystem_usage = summary
                        publish_filesystem_usage(summary)
                        logging.debug(
                            "Published filesystem summary mounted_on=%s total_bytes=%s used_bytes=%s "
                            "available_bytes=%s used_percent=%s available_percent=%.2f",
                            summary.mounted_on,
                            summary.bytes_total,
                            summary.bytes_used,
                            summary.bytes_available,
                            summary.used_percent,
                            summary.available_percent,
                        )
                    else:
                        row = parse_lfs_df_line(line)
                        if row is None:
                            continue
                        rows.append(row)
                        publish_usage_row(row)
                        logging.debug(
                            "Published %s %s uuid=%s mounted_on=%s total_bytes=%s used_bytes=%s "
                            "available_bytes=%s used_percent=%s available_percent=%.2f",
                            row.target_type,
                            row.target_index,
                            row.uuid,
                            row.mounted_on,
                            row.bytes_total,
                            row.bytes_used,
                            row.bytes_available,
                            row.used_percent,
                            row.available_percent,
                        )
                else:
                    stderr_lines.append(line)
                    logging.debug("Command stderr: %s", line)
    finally:
        selector.close()

    return_code = process.wait()
    stderr = "\n".join(stderr_lines)
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command, stderr=stderr)

    for row in rows:
        logging.debug(
            "Parsed %s %s uuid=%s mounted_on=%s total_bytes=%s used_bytes=%s "
            "available_bytes=%s used_percent=%s available_percent=%.2f",
            row.target_type,
            row.target_index,
            row.uuid,
            row.mounted_on,
            row.bytes_total,
            row.bytes_used,
            row.bytes_available,
            row.used_percent,
            row.available_percent,
        )
    if filesystem_usage is not None:
        logging.debug(
            "Parsed filesystem summary mounted_on=%s total_bytes=%s used_bytes=%s "
            "available_bytes=%s used_percent=%s available_percent=%.2f",
            filesystem_usage.mounted_on,
            filesystem_usage.bytes_total,
            filesystem_usage.bytes_used,
            filesystem_usage.bytes_available,
            filesystem_usage.used_percent,
            filesystem_usage.available_percent,
        )
    return rows


def clear_removed_labelsets(
    metric: Gauge,
    previous_labels: set[tuple[str, str, str, str]],
    current_labels: set[tuple[str, str, str, str]],
) -> None:
    for label_values in previous_labels - current_labels:
        metric.remove(*label_values)


def publish_usage(rows: Iterable[LustreTargetUsage], previous_labels: set[tuple[str, str, str, str]]) -> set[tuple[str, str, str, str]]:
    current_labels: set[tuple[str, str, str, str]] = set()

    for row in rows:
        labels = publish_usage_row(row)
        current_labels.add(labels)

    for metric in (BYTES_TOTAL, BYTES_USED, BYTES_AVAILABLE, USED_PERCENT, AVAILABLE_PERCENT):
        clear_removed_labelsets(metric, previous_labels, current_labels)

    return current_labels


def publish_usage_row(row: LustreTargetUsage) -> tuple[str, str, str, str]:
    labels = (row.target_type, row.target_index, row.uuid, row.mounted_on)
    BYTES_TOTAL.labels(*labels).set(row.bytes_total)
    BYTES_USED.labels(*labels).set(row.bytes_used)
    BYTES_AVAILABLE.labels(*labels).set(row.bytes_available)
    USED_PERCENT.labels(*labels).set(row.used_percent)
    AVAILABLE_PERCENT.labels(*labels).set(row.available_percent)
    return labels


def publish_filesystem_usage(row: LustreFilesystemUsage) -> tuple[str]:
    labels = (row.mounted_on,)
    FILESYSTEM_BYTES_TOTAL.labels(*labels).set(row.bytes_total)
    FILESYSTEM_BYTES_USED.labels(*labels).set(row.bytes_used)
    FILESYSTEM_BYTES_AVAILABLE.labels(*labels).set(row.bytes_available)
    FILESYSTEM_USED_PERCENT.labels(*labels).set(row.used_percent)
    FILESYSTEM_AVAILABLE_PERCENT.labels(*labels).set(row.available_percent)
    return labels


def collection_loop(
    lfs_command: str,
    mount_path: str,
    interval_seconds: int,
    timeout_seconds: int,
    stop_event: threading.Event,
) -> None:
    previous_labels: set[tuple[str, str, str, str]] = set()
    next_run = time.monotonic()

    while not stop_event.is_set():
        now = time.monotonic()
        if now < next_run and stop_event.wait(next_run - now):
            break

        started = time.monotonic()
        try:
            logging.debug(
                "Starting Lustre usage collection mount=%s interval_seconds=%d timeout_seconds=%d",
                mount_path,
                interval_seconds,
                timeout_seconds,
            )
            rows = collect_lustre_usage(lfs_command, mount_path, timeout_seconds)
            previous_labels = publish_usage(rows, previous_labels)
            SCRAPE_SUCCESS.set(1)
            logging.info("Collected %d Lustre MDT/OST rows", len(rows))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            SCRAPE_SUCCESS.set(0)
            logging.exception("Failed to collect Lustre target usage: %s", exc)
        finally:
            finished = time.monotonic()
            SCRAPE_DURATION_SECONDS.set(finished - started)
            SCRAPE_LAST_RUN_TIMESTAMP_SECONDS.set(time.time())
            next_run = started + interval_seconds
            if next_run < finished:
                next_run = finished
            logging.debug(
                "Finished Lustre usage collection duration_seconds=%.3f next_run_in_seconds=%.3f",
                finished - started,
                max(0.0, next_run - finished),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export Lustre MDT and OST capacity metrics from lfs df -h."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Exporter listen port. Default: {DEFAULT_PORT}")
    parser.add_argument("--addr", default=DEFAULT_ADDR, help=f"Exporter listen address. Default: {DEFAULT_ADDR}")
    parser.add_argument("--mount", default=DEFAULT_MOUNT_PATH, help=f"Lustre mount path. Default: {DEFAULT_MOUNT_PATH}")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS, help=f"Collection interval. Default: {DEFAULT_INTERVAL_SECONDS}")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS, help=f"lfs df timeout. Default: {DEFAULT_TIMEOUT_SECONDS}")
    parser.add_argument("--lfs-command", default=DEFAULT_LFS_COMMAND, help=f"lfs binary path. Default: {DEFAULT_LFS_COMMAND}")
    parser.add_argument(
        "--log-level",
        type=str.upper,
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Log level. Default: INFO",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.interval_seconds <= 0:
        raise SystemExit("--interval-seconds must be greater than zero")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be greater than zero")

    start_http_server(args.port, addr=args.addr)
    logging.info("Listening on %s:%d", args.addr, args.port)

    stop_event = threading.Event()
    try:
        collection_loop(
            lfs_command=args.lfs_command,
            mount_path=args.mount,
            interval_seconds=args.interval_seconds,
            timeout_seconds=args.timeout_seconds,
            stop_event=stop_event,
        )
    except KeyboardInterrupt:
        logging.info("Stopping exporter")
        stop_event.set()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
