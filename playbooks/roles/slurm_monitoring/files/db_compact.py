#!/usr/bin/env python3
"""
Retain and optimize Slurm monitoring MySQL data.

Ansible provisions the monitoring database schema. This script only deletes old
rows and optionally runs MySQL table maintenance.
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict

from db_adapter_controller import get_adapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("db_compact")


def get_db_size(db) -> int:
    """Return database size in bytes from information_schema."""
    try:
        row = db.fetchone(
            """
            SELECT SUM(data_length + index_length) AS size
            FROM information_schema.tables
            WHERE table_schema = %s
            """,
            (db.config["database"],),
        )
        return int(row["size"]) if row and row["size"] else 0
    except Exception as exc:
        logger.warning("Failed to read database size: %s", exc)
        return 0


def format_size(bytes_size: int) -> str:
    """Format bytes as a human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"


def get_table_counts(db) -> Dict[str, int]:
    """Return row counts for monitoring tables."""
    counts = {}
    for table in ["jobs", "job_utilization"]:
        try:
            row = db.fetchone(f"SELECT COUNT(*) AS cnt FROM {table}")
            counts[table] = row["cnt"] if row else 0
        except Exception as exc:
            logger.warning("Failed to count table %s: %s", table, exc)
            counts[table] = 0
    return counts


def delete_in_batches(db, query: str, params: tuple, total: int, verbose: bool) -> int:
    """Delete rows in batches to avoid long MySQL locks."""
    deleted = 0
    batch_size = 10000
    while deleted < total:
        cursor = db.execute(query, (*params, batch_size))
        if cursor.rowcount <= 0:
            break
        deleted += cursor.rowcount
        if verbose:
            logger.info("Deleted %s/%s rows", min(deleted, total), total)
    return deleted


def compact_database(
    retention_days: int = 90,
    retention_util_days: int = 30,
    dry_run: bool = False,
    optimize: bool = False,
    analyze: bool = False,
    verbose: bool = False,
) -> Dict:
    """Delete old monitoring rows and optionally optimize/analyze MySQL tables."""
    results = {
        "jobs_deleted": 0,
        "utilization_deleted": 0,
        "initial_size": 0,
        "final_size": 0,
        "space_reclaimed": 0,
        "dry_run": dry_run,
        "errors": [],
    }

    try:
        db = get_adapter().connect()
        db.validate_schema()
    except Exception as exc:
        results["errors"].append(f"Failed to connect to database: {exc}")
        return results

    jobs_cutoff = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
    util_cutoff = (datetime.now() - timedelta(days=retention_util_days)).strftime("%Y-%m-%d %H:%M:%S")

    if verbose:
        logger.info("Jobs retention: %s days, cutoff %s", retention_days, jobs_cutoff)
        logger.info("Utilization retention: %s days, cutoff %s", retention_util_days, util_cutoff)

    results["initial_size"] = get_db_size(db)
    counts = get_table_counts(db)
    logger.info(
        "Initial database size: %s; jobs=%s, job_utilization=%s",
        format_size(results["initial_size"]),
        counts["jobs"],
        counts["job_utilization"],
    )

    try:
        row = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM jobs WHERE submit_time < %s AND state NOT IN ('RUNNING', 'PENDING')",
            (jobs_cutoff,),
        )
        jobs_count = row["cnt"] if row else 0
    except Exception as exc:
        jobs_count = 0
        results["errors"].append(f"Failed to count jobs: {exc}")

    try:
        row = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM job_utilization WHERE timestamp < %s",
            (util_cutoff,),
        )
        util_count = row["cnt"] if row else 0
    except Exception as exc:
        util_count = 0
        results["errors"].append(f"Failed to count utilization records: {exc}")

    logger.info("Jobs to delete: %s", jobs_count)
    logger.info("Utilization rows to delete: %s", util_count)

    if dry_run:
        logger.info("Dry run complete; no rows deleted")
        db.close()
        return results

    if util_count > 0:
        try:
            results["utilization_deleted"] = delete_in_batches(
                db,
                """
                DELETE FROM job_utilization
                WHERE timestamp < %s
                LIMIT %s
                """,
                (util_cutoff,),
                util_count,
                verbose,
            )
        except Exception as exc:
            results["errors"].append(f"Failed to delete utilization records: {exc}")
            logger.error("Failed to delete utilization records: %s", exc)

    if jobs_count > 0:
        try:
            results["jobs_deleted"] = delete_in_batches(
                db,
                """
                DELETE FROM jobs
                WHERE submit_time < %s AND state NOT IN ('RUNNING', 'PENDING')
                LIMIT %s
                """,
                (jobs_cutoff,),
                jobs_count,
                verbose,
            )
        except Exception as exc:
            results["errors"].append(f"Failed to delete jobs: {exc}")
            logger.error("Failed to delete jobs: %s", exc)

    if analyze:
        try:
            db.execute("ANALYZE TABLE jobs")
            db.execute("ANALYZE TABLE job_utilization")
        except Exception as exc:
            results["errors"].append(f"Failed to analyze tables: {exc}")
            logger.warning("Failed to analyze tables: %s", exc)

    if optimize:
        try:
            db.execute("OPTIMIZE TABLE jobs")
            db.execute("OPTIMIZE TABLE job_utilization")
        except Exception as exc:
            results["errors"].append(f"Failed to optimize tables: {exc}")
            logger.warning("Failed to optimize tables: %s", exc)

    results["final_size"] = get_db_size(db)
    results["space_reclaimed"] = results["initial_size"] - results["final_size"]
    logger.info("Final database size: %s", format_size(results["final_size"]))
    if results["space_reclaimed"] > 0:
        logger.info("Space reclaimed: %s", format_size(results["space_reclaimed"]))

    if verbose:
        counts = get_table_counts(db)
        logger.info("Final counts: jobs=%s, job_utilization=%s", counts["jobs"], counts["job_utilization"])

    db.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Retain and optimize Slurm monitoring MySQL data")
    parser.add_argument("--retention-days", type=int, default=90, help="Keep jobs for N days")
    parser.add_argument("--retention-util-days", type=int, default=30, help="Keep utilization samples for N days")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    parser.add_argument("--optimize", action="store_true", help="Run OPTIMIZE TABLE after deletion")
    parser.add_argument("--analyze", action="store_true", help="Run ANALYZE TABLE after deletion")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print detailed progress")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level",
    )
    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))
    results = compact_database(
        retention_days=args.retention_days,
        retention_util_days=args.retention_util_days,
        dry_run=args.dry_run,
        optimize=args.optimize,
        analyze=args.analyze,
        verbose=args.verbose,
    )

    if results["errors"]:
        for error in results["errors"]:
            logger.warning(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
