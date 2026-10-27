#!/usr/bin/env python3
"""
NCCL Inspector JSON dump collector.

Watches the shared NCCL Inspector dump directory for per-rank JSON dump
files, and ingests per-operation collective performance records into a
MySQL table following the analysis flow described in NIXT
(arXiv 2608.01449). Each JSON line carries the flattened schema:

    {"header": {id, comm_name, rank, n_ranks, nnodes},
     "metadata": {inspector_output_format_version, git_rev,
                  rec_mechanism, dump_timestamp_us, hostname, pid},
     "coll_perf": {coll, coll_sn, coll_msg_size_bytes, coll_exec_time_us,
                   coll_timing_source, coll_algobw_gbs, coll_busbw_gbs}}

p2p_perf lines are skipped, matching the NIXT exporter behavior.

Environment Variables:
    NCCL_INSPECTOR_DUMP_DIR   - Root dump directory (required). Expected
                                layout: <dir>/job-<slurm_jobid>/<hostname>-pid<pid>.log
    NCCL_INSPECTOR_DB_HOST    - MySQL host (required)
    NCCL_INSPECTOR_DB_PORT    - MySQL port (default: 3306)
    NCCL_INSPECTOR_DB_USER    - MySQL user (required)
    NCCL_INSPECTOR_DB_PASSWORD - MySQL password (required)
    NCCL_INSPECTOR_DB_NAME    - MySQL database (default: slurm_jobs)
    NCCL_INSPECTOR_POLL_INTERVAL - Scan interval in seconds (default: 30)
    NCCL_INSPECTOR_RETENTION_DAYS - Drop rows/dirs older than N days, 0 disables (default: 30)
    NCCL_INSPECTOR_STATE_FILE - Offset tracking file (default: /var/lib/nccl-inspector-collector/state.json)
"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import mysql.connector

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("nccl-inspector-collector")

DUMP_DIR = os.environ.get("NCCL_INSPECTOR_DUMP_DIR", "/config/metrics/nccl-inspector")
DB_HOST = os.environ.get("NCCL_INSPECTOR_DB_HOST", "")
DB_PORT = int(os.environ.get("NCCL_INSPECTOR_DB_PORT", "3306"))
DB_USER = os.environ.get("NCCL_INSPECTOR_DB_USER", "")
DB_PASSWORD = os.environ.get("NCCL_INSPECTOR_DB_PASSWORD", "")
DB_NAME = os.environ.get("NCCL_INSPECTOR_DB_NAME", "slurm_jobs")
POLL_INTERVAL = int(os.environ.get("NCCL_INSPECTOR_POLL_INTERVAL", "30"))
RETENTION_DAYS = int(os.environ.get("NCCL_INSPECTOR_RETENTION_DAYS", "30"))
STATE_FILE = os.environ.get(
    "NCCL_INSPECTOR_STATE_FILE", "/var/lib/nccl-inspector-collector/state.json"
)
BATCH_SIZE = 1000

TABLE_NAME = "nccl_inspector_coll_perf"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    comm_id VARCHAR(80) NOT NULL,
    comm_name VARCHAR(255) NOT NULL DEFAULT '',
    `rank` INT NOT NULL,
    n_ranks INT NOT NULL,
    nnodes INT NOT NULL,
    comm_type VARCHAR(16) NOT NULL,
    coll VARCHAR(32) NOT NULL,
    coll_sn BIGINT UNSIGNED NOT NULL,
    coll_msg_size_bytes BIGINT UNSIGNED NOT NULL,
    coll_exec_time_us BIGINT UNSIGNED NOT NULL,
    coll_timing_source VARCHAR(32) NOT NULL DEFAULT '',
    coll_algobw_gbs DOUBLE NOT NULL,
    coll_busbw_gbs DOUBLE NOT NULL,
    dump_timestamp_us BIGINT UNSIGNED NOT NULL,
    hostname VARCHAR(255) NOT NULL,
    pid BIGINT UNSIGNED NOT NULL,
    slurm_job_id VARCHAR(32) NOT NULL DEFAULT 'unknown',
    source_file VARCHAR(512) NOT NULL DEFAULT '',
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_op (slurm_job_id, hostname, pid, comm_id, `rank`, coll_sn),
    KEY idx_job (slurm_job_id),
    KEY idx_time (dump_timestamp_us),
    KEY idx_coll (coll, comm_type, coll_msg_size_bytes)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

INSERT_SQL = f"""
INSERT INTO {TABLE_NAME}
    (comm_id, comm_name, `rank`, n_ranks, nnodes, comm_type, coll, coll_sn,
     coll_msg_size_bytes, coll_exec_time_us, coll_timing_source,
     coll_algobw_gbs, coll_busbw_gbs, dump_timestamp_us, hostname, pid,
     slurm_job_id, source_file)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE id = id
"""

RETENTION_DELETE_SQL = f"DELETE FROM {TABLE_NAME} WHERE dump_timestamp_us < %s LIMIT 10000"

run = True


def signal_handler(signum, frame):
    global run
    logger.info("Shutting down...")
    run = False


def get_comm_type(n_ranks, nnodes):
    """Communication topology classification, per the NIXT exporter."""
    if n_ranks == 1:
        return "single-rank"
    if nnodes == 1:
        return "nvlink-only"
    if n_ranks == nnodes:
        return "hca-only"
    return "mixed"


def parse_record(line, slurm_job_id, source_file):
    """Parse one JSONL dump line into a row tuple, or None if skipped."""
    try:
        rec = json.loads(line)
    except json.JSONDecodeError as exc:
        logger.debug("Skipping invalid JSON in %s: %s", source_file, exc)
        return None
    try:
        header = rec["header"]
        metadata = rec["metadata"]
        coll_perf = rec["coll_perf"]
        n_ranks = int(header["n_ranks"])
        nnodes = int(header["nnodes"])
        return (
            str(header["id"]),
            str(header.get("comm_name", "")),
            int(header["rank"]),
            n_ranks,
            nnodes,
            get_comm_type(n_ranks, nnodes),
            str(coll_perf["coll"]),
            int(coll_perf["coll_sn"]),
            int(coll_perf["coll_msg_size_bytes"]),
            int(coll_perf["coll_exec_time_us"]),
            str(coll_perf.get("coll_timing_source", "")),
            float(coll_perf["coll_algobw_gbs"]),
            float(coll_perf["coll_busbw_gbs"]),
            int(metadata["dump_timestamp_us"]),
            str(metadata["hostname"]),
            int(metadata["pid"]),
            slurm_job_id,
            source_file,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(rec, dict) and "p2p_perf" in rec and "coll_perf" not in rec:
            return None
        logger.debug("Skipping invalid NCCL Inspector record in %s: %s", source_file, exc)
        return None


def job_id_for(path):
    """Derive slurm_job_id from the job-<id> parent directory name."""
    parent = Path(path).parent.name
    if parent.startswith("job-"):
        return parent[len("job-"):]
    return "unknown"


class State:
    """Per-file ingestion offsets persisted across restarts."""

    def __init__(self, path):
        self.path = path
        self.offsets = {}
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                self.offsets = data
        except (OSError, json.JSONDecodeError):
            pass

    def get(self, key, default=None):
        return self.offsets.get(key, default)

    def save(self):
        tmp = self.path + ".tmp"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(self.offsets, f)
        os.replace(tmp, self.path)


def connect():
    while run:
        try:
            conn = mysql.connector.connect(
                host=DB_HOST, port=DB_PORT, user=DB_USER,
                password=DB_PASSWORD, database=DB_NAME, connection_timeout=10,
            )
            logger.info(f"Connected to MySQL {DB_HOST}:{DB_PORT}/{DB_NAME}")
            return conn
        except mysql.connector.Error as e:
            logger.error(f"Could not connect to database: {e}; retrying in 30s")
            time.sleep(30)
    sys.exit(0)


@contextmanager
def transaction(conn):
    """Commit a database transaction or roll it back if any operation fails."""
    try:
        with conn.cursor() as cursor:
            yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def flush_batch(cursor, rows):
    if rows:
        cursor.executemany(INSERT_SQL, rows)
        count = len(rows)
        rows.clear()
        return count
    return 0


def ingest_plain_file(conn, path, state):
    """Tail a plain .log dump file from the last known offset."""
    offset = state.get(path, 0)
    size = Path(path).stat().st_size
    if size < offset:
        offset = 0  # truncated/rotated file, start over
    if size == offset:
        return 0

    inserted = 0
    rows = []
    slurm_job_id = job_id_for(path)
    try:
        with transaction(conn) as cursor, open(path, "r", errors="replace") as f:
            f.seek(offset)
            new_offset = offset
            while True:
                line = f.readline()
                if not line:
                    break
                if not line.endswith("\n"):
                    # Trailing partial line: the plugin was mid-write when we
                    # polled. Keep the offset after the last complete line so
                    # this one is ingested on the next poll.
                    break
                if row := parse_record(line, slurm_job_id, path):
                    rows.append(row)
                    if len(rows) >= BATCH_SIZE:
                        inserted += flush_batch(cursor, rows)
                new_offset = f.tell()
            inserted += flush_batch(cursor, rows)
    except OSError as e:
        logger.error(f"Error reading {path}: {e}")
        return 0
    state.offsets[path] = new_offset
    state.save()
    return inserted


def apply_retention(conn):
    """Drop rows and finished job directories older than the retention window."""
    if RETENTION_DAYS <= 0:
        return
    cutoff_us = int((time.time() - RETENTION_DAYS * 86400) * 1e6)
    total = 0
    while True:
        with transaction(conn) as cursor:
            cursor.execute(RETENTION_DELETE_SQL, (cutoff_us,))
            deleted = cursor.rowcount
        total += deleted
        if deleted < 10000:
            break
    if total:
        logger.info(f"Retention removed {total} rows older than {RETENTION_DAYS} days")

    cutoff_s = time.time() - RETENTION_DAYS * 86400
    for job_dir in Path(DUMP_DIR).glob("job-*"):
        if not job_dir.is_dir():
            continue
        try:
            latest_mtime = job_dir.stat().st_mtime
            for root, dirs, files in os.walk(job_dir):
                for name in dirs + files:
                    latest_mtime = max(latest_mtime, Path(root, name).stat().st_mtime)
            if latest_mtime < cutoff_s:
                subprocess.run(["sudo", "-n", "rm", "-rf", "--", str(job_dir)], check=True)
                logger.info(f"Retention removed dump directory {job_dir}")
        except (OSError, subprocess.CalledProcessError) as e:
            logger.error(f"Error removing {job_dir}: {e}")


def scan(conn, state):
    total = 0
    for path in sorted(str(path) for path in Path(DUMP_DIR).rglob("*.log")):
        if not run:
            break
        total += ingest_plain_file(conn, path, state)
    if total:
        logger.info(f"Ingested {total} collective records")
    # Drop state entries for files removed by retention.
    stale = [k for k in state.offsets if not os.path.exists(k)]
    if stale:
        for k in stale:
            state.offsets.pop(k, None)
        state.save()


def main():
    if not all((DUMP_DIR, DB_HOST, DB_USER, DB_PASSWORD)):
        logger.error(
            "NCCL_INSPECTOR_DUMP_DIR, NCCL_INSPECTOR_DB_HOST, "
            "NCCL_INSPECTOR_DB_USER and NCCL_INSPECTOR_DB_PASSWORD are required"
        )
        sys.exit(1)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    state = State(STATE_FILE)
    conn = connect()
    with transaction(conn) as cursor:
        cursor.execute(DDL)
    logger.info(f"Ensured table {DB_NAME}.{TABLE_NAME}")

    last_retention = 0.0
    while run:
        try:
            if os.path.isdir(DUMP_DIR):
                scan(conn, state)
        except (mysql.connector.Error, OSError, json.JSONDecodeError) as e:
            logger.error(f"Scan failed: {e}")
            try:
                conn.ping(reconnect=True, attempts=3, delay=5)
            except mysql.connector.Error:
                conn = connect()
        if time.time() - last_retention > 3600:
            try:
                apply_retention(conn)
            except (mysql.connector.Error, OSError) as e:
                logger.error(f"Retention failed: {e}")
            last_retention = time.time()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
