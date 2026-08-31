#!/usr/bin/env python3
"""
Slurm Job Exporter with Database Storage

Collects job data from sacct and stores in database for Grafana visualization.
Supports hierarchical account structures (team/subteam/project).
Uses the Ansible-provisioned MySQL monitoring schema.

Usage:
    python slurm_job_exporter.py --interval 60

Environment:
    SLURM_DB_HOST       - MySQL host
    SLURM_DB_PORT       - MySQL port
    SLURM_DB_USER       - MySQL user
    SLURM_DB_PASSWORD   - MySQL password
    SLURM_DB_NAME       - MySQL database name

Grafana: Use the built-in MySQL datasource to query the database.
"""

import argparse
import logging
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from db_adapter_controller import get_adapter

try:
    from prometheus_client import Gauge, Counter, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('slurm_job_exporter')

SACCT_TERMINAL_STATES = [
    'BOOT_FAIL',
    'CANCELLED',
    'COMPLETED',
    'DEADLINE',
    'FAILED',
    'NODE_FAIL',
    'OUT_OF_MEMORY',
    'PREEMPTED',
    'REVOKED',
    'SPECIAL_EXIT',
    'TIMEOUT',
]


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class JobRecord:
    """A single job record from sacct."""
    job_id: str
    job_name: str
    user: str
    account: str  # Full hierarchical account path: ai/research/project1
    partition: str
    state: str
    exit_code: str = ""

    # Resource allocation
    num_nodes: int = 0
    num_cpus: int = 0
    num_gpus: int = 0
    node_list: str = ""  # Comma-separated list of nodes
    memory_requested: str = ""
    memory_used: str = ""

    # Timing
    submit_time: Optional[datetime] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    elapsed_seconds: int = 0
    wait_seconds: int = 0  # Time from submit to start

    # Cluster info
    cluster: str = ""
    qos: str = ""
    priority: int = 0

    # Derived hierarchy levels
    account_l1: str = ""  # Top level (e.g., "ai")
    account_l2: str = ""  # Second level (e.g., "research")
    account_l3: str = ""  # Third level (e.g., "project1")
    account_depth: int = 0  # How many levels deep

    # Utilization metrics (aggregated from NVML data)
    avg_gpu_util: float = 0.0
    max_gpu_util: float = 0.0
    avg_gpu_mem_util: float = 0.0
    avg_cpu_util: float = 0.0
    avg_mem_util_bytes: int = 0

    def __post_init__(self):
        """Parse hierarchical account structure."""
        if self.account:
            parts = self.account.split('/')
            self.account_depth = len(parts)
            if len(parts) >= 1:
                self.account_l1 = parts[0]
            if len(parts) >= 2:
                self.account_l2 = parts[1]
            if len(parts) >= 3:
                self.account_l3 = parts[2]


@dataclass
class AccountHierarchy:
    """Represents an account in the hierarchy."""
    account_path: str  # Full path: ai/research/project1
    parent_path: str   # Parent: ai/research
    name: str          # Just the name: project1
    level: int         # Depth: 3


# ============================================================================
# Database Operations (using db_adapter)
# ============================================================================

class JobDatabase:
    """Database for job records with hierarchical account support.

    Uses the MySQL schema provisioned by Ansible.
    """

    def __init__(self):
        """Initialize database connection and validate the expected schema."""
        self.db = get_adapter().connect()
        self.db.validate_schema()
        logger.info("Database initialized")

    def upsert_job(self, job: JobRecord) -> None:
        """Insert or update a job record."""
        now = datetime.now().isoformat()

        # Use MySQL syntax with backticks for reserved words
        self.db.execute("""
            INSERT INTO jobs (
                job_id, name, `user`, account, `partition`, state, exit_code,
                num_nodes, num_cpus, num_gpus, node_list,
                submit_time, start_time, end_time, elapsed_seconds,
                cluster, qos, priority,
                account_l1, account_l2, account_l3,
                avg_gpu_util, max_gpu_util, avg_gpu_mem_util,
                avg_cpu_util, avg_mem_util_bytes, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                state = VALUES(state),
                exit_code = VALUES(exit_code),
                submit_time = COALESCE(VALUES(submit_time), submit_time),
                start_time = COALESCE(VALUES(start_time), start_time),
                end_time = VALUES(end_time),
                elapsed_seconds = VALUES(elapsed_seconds),
                avg_gpu_util = VALUES(avg_gpu_util),
                max_gpu_util = VALUES(max_gpu_util),
                avg_gpu_mem_util = VALUES(avg_gpu_mem_util),
                avg_cpu_util = VALUES(avg_cpu_util),
                avg_mem_util_bytes = VALUES(avg_mem_util_bytes),
                updated_at = VALUES(updated_at)
        """, (
            parse_job_id(job.job_id), job.job_name, job.user, job.account, job.partition,
            job.state, job.exit_code, job.num_nodes, job.num_cpus, job.num_gpus,
            job.node_list,
            job.submit_time.isoformat() if job.submit_time else None,
            job.start_time.isoformat() if job.start_time else None,
            job.end_time.isoformat() if job.end_time else None,
            job.elapsed_seconds,
            job.cluster, job.qos, job.priority,
            job.account_l1, job.account_l2, job.account_l3,
            job.avg_gpu_util, job.max_gpu_util, job.avg_gpu_mem_util,
            job.avg_cpu_util, job.avg_mem_util_bytes, now
        ))

    def upsert_jobs(self, jobs: List[JobRecord]) -> int:
        """Bulk insert/update job records."""
        if not jobs:
            return 0

        for job in jobs:
            self.upsert_job(job)
        return len(jobs)

    def get_running_job_ids(self) -> List[int]:
        """Get jobs still marked running in the monitoring database."""
        rows = self.db.fetchall("SELECT job_id FROM jobs WHERE state = 'RUNNING'")
        return [int(row['job_id']) for row in rows if row.get('job_id') is not None]

    def update_job_utilization(self, job_id: str, avg_gpu: float, max_gpu: float,
                               avg_gpu_mem: float, avg_cpu: float, avg_mem: int) -> None:
        """Update utilization metrics for a job."""
        now = datetime.now().isoformat()
        self.db.execute("""
            UPDATE jobs SET
                avg_gpu_util = %s,
                max_gpu_util = %s,
                avg_gpu_mem_util = %s,
                avg_cpu_util = %s,
                avg_mem_util_bytes = %s,
                updated_at = %s
            WHERE job_id = %s
        """, (avg_gpu, max_gpu, avg_gpu_mem, avg_cpu, avg_mem, now, parse_job_id(job_id)))

    def aggregate_job_utilization(self, job_id: int) -> Dict[str, float]:
        """Aggregate utilization metrics from job_utilization for a job."""
        row = self.db.fetchone("""
            SELECT
                AVG(gpu_util) as avg_gpu,
                MAX(gpu_util) as max_gpu,
                AVG(gpu_mem_util) as avg_gpu_mem,
                (
                    SELECT SUM(host_cpu.avg_cpu)
                    FROM (
                        SELECT hostname, AVG(cpu_util) as avg_cpu
                        FROM job_utilization
                        WHERE job_id = %s
                        GROUP BY hostname
                    ) host_cpu
                ) as total_avg_cpu,
                (
                    SELECT num_cpus
                    FROM jobs
                    WHERE job_id = %s
                ) as num_cpus,
                AVG(mem_util_bytes) as avg_mem
            FROM job_utilization
            WHERE job_id = %s
        """, (job_id, job_id, job_id))

        if not row:
            return {
                'avg_gpu': 0.0, 'max_gpu': 0.0, 'avg_gpu_mem': 0.0,
                'avg_cpu': 0.0, 'avg_mem': 0
            }

        num_cpus = int(row['num_cpus'] or 0)
        total_avg_cpu = float(row['total_avg_cpu'] or 0.0)
        avg_cpu = total_avg_cpu / num_cpus if num_cpus > 0 else 0.0

        return {
            'avg_gpu': round(row['avg_gpu'] or 0.0, 1),
            'max_gpu': round(row['max_gpu'] or 0.0, 1),
            'avg_gpu_mem': round(row['avg_gpu_mem'] or 0.0, 1),
            'avg_cpu': round(avg_cpu, 1),
            'avg_mem': int(row['avg_mem'] or 0)
        }

    def get_completed_jobs_needing_aggregation(self, hours: int = 24) -> List[int]:
        """Get recently completed jobs that need utilization aggregated."""
        rows = self.db.fetchall("""
            SELECT DISTINCT j.job_id
            FROM jobs j
            INNER JOIN job_utilization u ON j.job_id = u.job_id
            WHERE j.state IN ('COMPLETED', 'FAILED', 'TIMEOUT', 'NODE_FAIL', 'OUT_OF_MEMORY')
              AND j.avg_gpu_util = 0
              AND j.end_time > DATE_SUB(NOW(), INTERVAL %s HOUR)
            LIMIT 1000
        """, (hours,))
        return [row['job_id'] for row in rows]

    def update_account_hierarchy(self, accounts: List[str]) -> None:
        """Update account hierarchy from a list of account paths.

        Note: This is a simplified version - the full hierarchy table
        is optional and mainly used for recursive queries.
        """
        # For now, just log the unique accounts
        unique_accounts = set(a for a in accounts if a)
        logger.debug(f"Seen {len(unique_accounts)} unique accounts")

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        stats = {}

        # Total jobs
        row = self.db.fetchone("SELECT COUNT(*) as cnt FROM jobs")
        stats['total_jobs'] = row['cnt'] if row else 0

        # Jobs by state
        rows = self.db.fetchall("SELECT state, COUNT(*) as cnt FROM jobs GROUP BY state")
        for row in rows:
            state = row['state'] or 'unknown'
            stats[f'jobs_{state.lower()}'] = row['cnt']

        # Unique accounts
        row = self.db.fetchone("SELECT COUNT(DISTINCT account) as cnt FROM jobs")
        stats['unique_accounts'] = row['cnt'] if row else 0

        # Date range
        row = self.db.fetchone("SELECT MIN(submit_time) as min_t, MAX(submit_time) as max_t FROM jobs")
        if row:
            stats['earliest_job'] = row['min_t']
            stats['latest_job'] = row['max_t']

        return stats

    def close(self) -> None:
        """Close database connection."""
        self.db.close()


# ============================================================================
# Slurm Data Collection (sacct)
# ============================================================================

def parse_job_id(job_id_str: str) -> int:
    """Parse Slurm job ID, handling array jobs.

    Array jobs have IDs like '1953_[4-5]' or '1953_4'.
    Returns the base job ID as an integer.
    """
    if not job_id_str:
        return 0
    # Extract base job ID before underscore (array job delimiter)
    base_id = job_id_str.split('_')[0]
    try:
        return int(base_id)
    except ValueError:
        return 0


def parse_slurm_time(time_str: str) -> Optional[datetime]:
    """Parse Slurm timestamp formats."""
    if not time_str or time_str in ('Unknown', 'None', 'N/A'):
        return None

    formats = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%dT%H:%M',
    ]

    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue

    return None


def parse_elapsed(elapsed_str: str) -> int:
    """Parse Slurm elapsed time format (D-HH:MM:SS or HH:MM:SS) to seconds."""
    if not elapsed_str or elapsed_str in ('Unknown', 'None', 'N/A', ''):
        return 0

    try:
        # Handle days format: D-HH:MM:SS
        days = 0
        if '-' in elapsed_str:
            parts = elapsed_str.split('-')
            days = int(parts[0])
            elapsed_str = parts[1]

        # Handle HH:MM:SS or MM:SS
        parts = elapsed_str.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
        elif len(parts) == 2:
            hours, minutes, seconds = 0, int(parts[0]), int(parts[1])
        else:
            return 0

        return days * 86400 + hours * 3600 + minutes * 60 + seconds
    except (ValueError, IndexError):
        return 0


def parse_tres(tres_str: str, key: str = 'gres/gpu') -> int:
    """Parse TRES string to extract resource count."""
    if not tres_str or tres_str in ('', 'Unknown', 'None'):
        return 0

    # Format: billing=8,cpu=4,gres/gpu=2,mem=64G,node=1
    for part in tres_str.split(','):
        if '=' in part:
            k, v = part.split('=', 1)
            if k.strip() == key:
                try:
                    return int(v)
                except ValueError:
                    return 0
    return 0


def collect_sacct(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    states: Optional[List[str]] = None,
    cluster: str = "",
    job_ids: Optional[List[int]] = None
) -> List[JobRecord]:
    """Collect job records from sacct."""
    jobs = []

    # Build sacct command
    cmd = [
        'sacct',
        '-P',  # Parseable output
        '--noheader',
        '-X',  # Allocations only; skip batch/extern job steps
        '--delimiter=|',
        '-a',  # All users
        '--format=JobID,JobName,User,Account,Partition,State,ExitCode,'
                'NNodes,NCPUs,ReqTRES,MaxRSS,'
                'Submit,Start,End,Elapsed,'
                'Cluster,QOS,Priority'
    ]

    if job_ids:
        cmd.extend(['-j', ','.join(str(job_id) for job_id in job_ids)])
    else:
        if start_time:
            cmd.extend(['-S', start_time.strftime('%Y-%m-%dT%H:%M:%S')])
        else:
            # Default to last 24 hours
            cmd.extend(['-S', (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')])

        if end_time:
            cmd.extend(['-E', end_time.strftime('%Y-%m-%dT%H:%M:%S')])

        if states:
            cmd.extend(['-s', ','.join(states)])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.error(f"sacct failed: {result.stderr}")
            return jobs

        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue

            parts = line.split('|')
            if len(parts) < 17:
                continue

            # Skip job steps and array tasks (only want main/parent jobs)
            # Steps have '.' (e.g., 1953.batch), array tasks have '_' (e.g., 1953_4)
            # NVML exporter uses base job IDs, so we must match that
            job_id = parts[0]
            if '.' in job_id or '_' in job_id:
                continue

            try:
                submit_time = parse_slurm_time(parts[11])
                start_time_parsed = parse_slurm_time(parts[12])
                end_time_parsed = parse_slurm_time(parts[13])

                # Calculate wait time
                wait_seconds = 0
                if submit_time and start_time_parsed:
                    wait_seconds = int((start_time_parsed - submit_time).total_seconds())
                    if wait_seconds < 0:
                        wait_seconds = 0

                job = JobRecord(
                    job_id=job_id,
                    job_name=parts[1],
                    user=parts[2],
                    account=parts[3],
                    partition=parts[4],
                    state=parts[5].split()[0] if parts[5] else '',  # Remove state reason
                    exit_code=parts[6],
                    num_nodes=int(parts[7]) if parts[7].isdigit() else 0,
                    num_cpus=int(parts[8]) if parts[8].isdigit() else 0,
                    num_gpus=parse_tres(parts[9], 'gres/gpu'),
                    memory_requested=parts[9],
                    memory_used=parts[10],
                    submit_time=submit_time,
                    start_time=start_time_parsed,
                    end_time=end_time_parsed,
                    elapsed_seconds=parse_elapsed(parts[14]),
                    wait_seconds=wait_seconds,
                    cluster=parts[15] or cluster,
                    qos=parts[16],
                    priority=int(parts[17]) if len(parts) > 17 and parts[17].isdigit() else 0
                )
                jobs.append(job)

            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse job line: {e}")
                continue

    except subprocess.TimeoutExpired:
        logger.error("sacct command timed out")
    except FileNotFoundError:
        logger.error("sacct command not found")
    except Exception as e:
        logger.error(f"Failed to collect sacct data: {e}")

    return jobs


def collect_running_jobs(cluster: str = "") -> List[JobRecord]:
    """Collect currently running/pending jobs from squeue."""
    jobs = []

    cmd = [
        'squeue',
        '-h',
        '-o', '%i|%j|%u|%a|%P|%T|%D|%C|%b|%V|%S|%r|%Q'
        # JobID|Name|User|Account|Partition|State|Nodes|CPUs|Gres|Submit|Start|Reason|Priority
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.error(f"squeue failed: {result.stderr}")
            return jobs

        for line in result.stdout.strip().split('\n'):
            if not line.strip():
                continue

            parts = line.split('|')
            if len(parts) < 10:
                continue

            # Skip array tasks (e.g., 1953_4) - only want parent jobs
            job_id = parts[0]
            if '_' in job_id:
                continue

            try:
                # Parse GPU from gres string (e.g., "gpu:4")
                num_gpus = 0
                gres = parts[8] if len(parts) > 8 else ""
                if gres:
                    match = re.search(r'gpu:?(\d+)?', gres.lower())
                    if match:
                        num_gpus = int(match.group(1)) if match.group(1) else 1

                job = JobRecord(
                    job_id=parts[0],
                    job_name=parts[1],
                    user=parts[2],
                    account=parts[3],
                    partition=parts[4],
                    state=parts[5],
                    num_nodes=int(parts[6]) if parts[6].isdigit() else 0,
                    num_cpus=int(parts[7]) if parts[7].isdigit() else 0,
                    num_gpus=num_gpus,
                    submit_time=parse_slurm_time(parts[9]) if len(parts) > 9 else None,
                    start_time=parse_slurm_time(parts[10]) if len(parts) > 10 else None,
                    priority=int(parts[12]) if len(parts) > 12 and parts[12].isdigit() else 0,
                    cluster=cluster
                )
                jobs.append(job)

            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse squeue line: {e}")
                continue

    except Exception as e:
        logger.error(f"Failed to collect squeue data: {e}")

    return jobs


# ============================================================================
# Prometheus Metrics (Optional)
# ============================================================================

class JobMetrics:
    """Prometheus metrics for job data."""

    def __init__(self, prefix: str = "slurm"):
        if not PROMETHEUS_AVAILABLE:
            return

        self.jobs_collected = Counter(
            f'{prefix}_jobs_collected_total',
            'Total jobs collected',
            ['cluster_name']
        )

        self.collection_duration = Gauge(
            f'{prefix}_job_collection_duration_seconds',
            'Time spent collecting job data',
            ['cluster_name']
        )

        self.jobs_in_db = Gauge(
            f'{prefix}_jobs_in_database',
            'Total jobs in database',
            ['cluster_name', 'state']
        )

    def update(self, cluster: str, stats: Dict):
        """Update Prometheus metrics."""
        if not PROMETHEUS_AVAILABLE:
            return

        # Jobs by state
        for key, value in stats.items():
            if key.startswith('jobs_'):
                state = key.replace('jobs_', '').upper()
                self.jobs_in_db.labels(cluster_name=cluster, state=state).set(value)


# ============================================================================
# Main Collector
# ============================================================================

class SlurmJobCollector:
    """Main collector that fetches jobs and stores in database."""

    def __init__(
        self,
        cluster: str = "",
        lookback_hours: int = 24,
        collect_running: bool = True
    ):
        self.db = JobDatabase()
        self.cluster = cluster or self._detect_cluster()
        self.lookback_hours = lookback_hours
        self.collect_running = collect_running
        self.metrics = JobMetrics() if PROMETHEUS_AVAILABLE else None

    def _detect_cluster(self) -> str:
        """Detect cluster name from hostname (e.g., 'controller-1' -> 'controller')."""
        return platform.node().rsplit('-', 1)[0]

    def collect(self) -> Dict[str, Any]:
        """Run a collection cycle."""
        start_time = time.time()
        results = {
            'jobs_collected': 0,
            'accounts_updated': 0,
            'errors': []
        }

        try:
            # Collect completed/historical jobs from sacct
            logger.info(f"Collecting jobs from last {self.lookback_hours} hours...")

            sacct_jobs = collect_sacct(
                start_time=datetime.now() - timedelta(hours=self.lookback_hours),
                states=SACCT_TERMINAL_STATES,
                cluster=self.cluster
            )
            # Keep this defensive filter in case Slurm returns state variants.
            sacct_jobs = [job for job in sacct_jobs if job.state not in ('RUNNING', 'PENDING')]

            # Collect running/pending jobs
            stale_jobs = []
            if self.collect_running:
                running_jobs = collect_running_jobs(cluster=self.cluster)
                running_job_ids = {parse_job_id(job.job_id) for job in running_jobs}
                db_running_job_ids = set(self.db.get_running_job_ids())
                stale_running_job_ids = sorted(db_running_job_ids - running_job_ids)

                if stale_running_job_ids:
                    logger.info(
                        f"Refreshing {len(stale_running_job_ids)} stale running jobs from sacct..."
                    )
                    for offset in range(0, len(stale_running_job_ids), 500):
                        stale_jobs.extend(collect_sacct(
                            cluster=self.cluster,
                            job_ids=stale_running_job_ids[offset:offset + 500]
                        ))

                    # Keep this defensive filter in case sacct still reports a non-terminal state.
                    stale_jobs = [
                        job for job in stale_jobs
                        if job.state not in ('RUNNING', 'PENDING')
                    ]

                all_jobs = running_jobs + sacct_jobs + stale_jobs
            else:
                all_jobs = sacct_jobs

            # Store in database
            count = self.db.upsert_jobs(all_jobs)
            results['jobs_collected'] = count
            results['stale_running_refreshed'] = len(stale_jobs)

            # Update account hierarchy
            accounts = list(set(j.account for j in all_jobs if j.account))
            self.db.update_account_hierarchy(accounts)
            results['accounts_updated'] = len(accounts)

            # Aggregate utilization for completed jobs
            try:
                jobs_to_aggregate = self.db.get_completed_jobs_needing_aggregation(
                    hours=self.lookback_hours
                )
                aggregated_count = 0

                for job_id in jobs_to_aggregate:
                    metrics = self.db.aggregate_job_utilization(job_id)
                    self.db.update_job_utilization(
                        str(job_id),
                        metrics['avg_gpu'],
                        metrics['max_gpu'],
                        metrics['avg_gpu_mem'],
                        metrics['avg_cpu'],
                        metrics['avg_mem']
                    )
                    aggregated_count += 1

                results['jobs_aggregated'] = aggregated_count
                if aggregated_count > 0:
                    logger.info(f"Aggregated utilization for {aggregated_count} jobs")
            except Exception as e:
                logger.error(f"Aggregation failed: {e}")
                results['errors'].append(f"Aggregation: {str(e)}")

            # Update metrics
            if self.metrics:
                duration = time.time() - start_time
                self.metrics.collection_duration.labels(cluster_name=self.cluster).set(duration)
                self.metrics.jobs_collected.labels(cluster_name=self.cluster).inc(count)
                stats = self.db.get_stats()
                self.metrics.update(self.cluster, stats)

            logger.info(f"Collected {count} jobs in {time.time() - start_time:.2f}s")

        except Exception as e:
            logger.error(f"Collection failed: {e}")
            results['errors'].append(str(e))

        return results

    def close(self) -> None:
        """Clean up resources."""
        self.db.close()


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Slurm Job Exporter with database storage for Grafana',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --interval 300
  %(prog)s --lookback 48 --once

Environment Variables:
  SLURM_DB_HOST       MySQL host
  SLURM_DB_PORT       MySQL port (default: 3306)
  SLURM_DB_USER       MySQL user
  SLURM_DB_PASSWORD   MySQL password
  SLURM_DB_NAME       MySQL database name

Grafana Setup:
  1. Add the built-in MySQL datasource pointing to the monitoring database
  2. Use SQL queries to visualize job data

Example Queries:
  -- All jobs under 'ai' team:
  SELECT * FROM jobs WHERE account LIKE 'ai/%%'

  -- Aggregate by top-level account:
  SELECT account_l1, SUM(elapsed_seconds * num_gpus) as gpu_seconds
  FROM jobs GROUP BY account_l1
"""
    )

    parser.add_argument(
        '--port', '-p',
        type=int,
        default=9902,
        help='Prometheus metrics port (default: 9902)'
    )

    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=300,
        help='Collection interval in seconds (default: 300)'
    )

    parser.add_argument(
        '--lookback',
        type=int,
        default=24,
        help='Hours of job history to collect (default: 24)'
    )

    parser.add_argument(
        '--cluster', '-c',
        default='',
        help='Cluster name (auto-detected if not set)'
    )

    parser.add_argument(
        '--once',
        action='store_true',
        help='Collect once and exit'
    )

    parser.add_argument(
        '--no-prometheus',
        action='store_true',
        help='Disable Prometheus metrics endpoint'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )

    args = parser.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Create collector
    collector = SlurmJobCollector(
        cluster=args.cluster,
        lookback_hours=args.lookback
    )

    if args.once:
        result = collector.collect()
        print(f"Collection complete: {result}")

        # Print database stats
        stats = collector.db.get_stats()
        print("\nDatabase stats:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return 0

    # Start Prometheus endpoint
    if not args.no_prometheus and PROMETHEUS_AVAILABLE:
        try:
            start_http_server(args.port)
            logger.info(f"Prometheus metrics on port {args.port}")
        except OSError as e:
            logger.warning(f"Could not start Prometheus server: {e}")

    # Handle signals
    stop_event = threading.Event()

    def signal_handler(signum, frame):
        logger.info("Shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Collection loop
    logger.info(f"Starting collection loop (interval: {args.interval}s)")

    while not stop_event.is_set():
        collector.collect()
        stop_event.wait(args.interval)

    logger.info("Exporter stopped")
    return 0


if __name__ == '__main__':
    sys.exit(main())
