#!/usr/bin/env python3
"""
NVML/CPU Metrics Exporter for Slurm Jobs

Collects per-job CPU, memory, and GPU utilization and stores it in central MySQL.
Only node-level metrics exported to Prometheus to avoid cardinality explosion.
Runs on each compute node when Slurm job monitoring is enabled.

Environment Variables:
    CPU_ONLY_MODE           - Set to "true" for nodes without NVIDIA GPUs (default: false)
    SCONTROL_PATH           - Path to scontrol binary
    METRICS_PORT            - Prometheus metrics port (default: 9800)
    SCRAPE_INTERVAL         - Metrics collection interval in seconds (default: 15)

    # MySQL database
    SLURM_DB_HOST           - MySQL host (required)
    SLURM_DB_PORT           - MySQL port (default: 3306)
    SLURM_DB_USER           - MySQL user (default: slurm)
    SLURM_DB_PASSWORD       - MySQL password (required)
    SLURM_DB_NAME           - MySQL database name (default: slurm_jobs)
    SLURM_NVML_DB_INTERVAL  - Database write interval in seconds (default: 60)
"""

import os
import time
import socket
import signal
import sys
import logging
import psutil
import subprocess
import re
import platform
import json
import glob
from datetime import datetime
from prometheus_client import start_http_server, Gauge, Counter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
CPU_ONLY_MODE = os.getenv("CPU_ONLY_MODE", "false").lower() == "true"
SCONTROL_PATH = os.getenv("SCONTROL_PATH")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9800"))
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))
DB_WRITE_INTERVAL = int(os.getenv("SLURM_NVML_DB_INTERVAL", "60"))

# Global state
cluster_name = "none"
hostname = socket.gethostname()
db_adapter = None

# Conditional NVML import
NVML_AVAILABLE = False
if not CPU_ONLY_MODE:
    try:
        import pynvml
        NVML_AVAILABLE = True
    except ImportError:
        logger.warning("pynvml not available, falling back to CPU_ONLY_MODE")
        CPU_ONLY_MODE = True

logger.info(f"SCONTROL_PATH: {SCONTROL_PATH}")
logger.info(f"CPU_ONLY_MODE: {CPU_ONLY_MODE}")
logger.info(f"NVML_AVAILABLE: {NVML_AVAILABLE}")
logger.info(f"METRICS_PORT: {METRICS_PORT}")
logger.info(f"SCRAPE_INTERVAL: {SCRAPE_INTERVAL}s")
logger.info(f"DB_WRITE_INTERVAL: {DB_WRITE_INTERVAL}s")

try:
    from db_adapter_compute import get_adapter
    db_adapter = get_adapter().connect()
    logger.info("Database adapter initialized for utilization storage")
except ImportError as e:
    logger.error(f"Could not import db_adapter_compute: {e}")
    logger.error("Database storage is required. Exiting.")
    sys.exit(1)
except Exception as e:
    logger.error(f"Could not connect to database: {e}")
    logger.error("Database storage is required. Exiting.")
    sys.exit(1)


# Keep shutdown cleanup explicit because this script owns both NVML and DB handles.
def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutting down...")
    if NVML_AVAILABLE and not CPU_ONLY_MODE:
        try:
            pynvml.nvmlShutdown()
        except Exception as e:
            logger.debug(f"Error during NVML shutdown: {e}")
    if db_adapter:
        try:
            db_adapter.close()
        except Exception as e:
            logger.debug(f"Error closing database: {e}")
    sys.exit(0)


# =============================================================================
# Prometheus Metrics - Node level only (bounded cardinality)
# =============================================================================

# Collection metrics
collection_duration_seconds = Gauge(
    "nvml_collection_duration_seconds",
    "Time spent collecting metrics",
    ["cluster_name", "hostname"]
)

db_writes_total = Counter(
    "nvml_db_writes_total",
    "Total number of database write operations",
    ["cluster_name", "hostname"]
)

db_write_errors_total = Counter(
    "nvml_db_write_errors_total",
    "Total number of database write errors",
    ["cluster_name", "hostname"]
)


def get_cluster_name():
    """Extract cluster name from SLURM node features or metadata."""
    cluster = "none"
    try:
        gpu_host = platform.node().split('.')[0]

        if not SCONTROL_PATH:
            logger.error("SCONTROL_PATH not set")
            return cluster

        scontrol_output = subprocess.check_output(
            [SCONTROL_PATH, "show", f"node={gpu_host}", "-o", "--json"],
            universal_newlines=True,
            timeout=30
        )
        slurm_node_data = json.loads(scontrol_output)

        features = slurm_node_data['nodes'][0].get('features', [])
        logger.debug(f"Node features: {features}")

        if isinstance(features, list):
            for feature in features:
                if '__' in feature:
                    cluster = feature.split("__")[1]
                    break
            if cluster == "none" and len(features) > 0:
                cluster = features[0]
        elif isinstance(features, str):
            cluster = features

    except subprocess.CalledProcessError as e:
        logger.error(f"Error running scontrol: {e}")
    except subprocess.TimeoutExpired:
        logger.error("scontrol command timed out")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error(f"Error parsing scontrol output: {e}")

    return cluster.strip() if cluster else "none"


def get_slurm_job_id_from_scontrol(pid):
    """Get SLURM job ID for a given PID using scontrol pidinfo."""
    try:
        if not SCONTROL_PATH:
            return "none"

        result = subprocess.run(
            [SCONTROL_PATH, "pidinfo", str(pid)],
            capture_output=True,
            text=True,
            check=True,
            timeout=10
        )
        output = result.stdout.strip()
        match = re.search(r"Slurm JobId=(\d+)", output)
        if match:
            return match.group(1)
        return "none"
    except subprocess.CalledProcessError:
        return "none"
    except subprocess.TimeoutExpired:
        return "none"


def get_slurm_job_pids_from_cgroups():
    """Discover SLURM job PIDs from cgroup filesystem (v1 and v2)."""
    job_pids = {}

    # Fallback only: prefer Slurm commands, but keep cgroups for edge cases where
    # squeue/listpids is incomplete or briefly unavailable on the compute node.
    cgroup_patterns = [
        "/sys/fs/cgroup/system.slice/slurmstepd.scope/job_*/",
        "/sys/fs/cgroup/system.slice/slurmstepd.scope/job_*/step_*/",
        "/sys/fs/cgroup/memory/slurm/uid_*/job_*/",
        "/sys/fs/cgroup/cpuacct/slurm/uid_*/job_*/",
        "/sys/fs/cgroup/cpu,cpuacct/slurm/uid_*/job_*/",
        "/sys/fs/cgroup/freezer/slurm/uid_*/job_*/",
        "/sys/fs/cgroup/*/slurm_*/job_*/",
    ]

    for pattern in cgroup_patterns:
        for job_path in glob.glob(pattern):
            job_id_match = re.search(r'job_(\d+)', job_path)
            if not job_id_match:
                continue
            job_id = job_id_match.group(1)

            if job_id in job_pids:
                continue

            for procs_file in ['cgroup.procs', 'tasks']:
                procs_path = os.path.join(job_path, procs_file)
                if os.path.exists(procs_path):
                    try:
                        with open(procs_path, 'r') as f:
                            pids = []
                            for line in f:
                                pid_str = line.strip()
                                if pid_str:
                                    try:
                                        pids.append(int(pid_str))
                                    except ValueError:
                                        continue
                            if pids:
                                job_pids[job_id] = pids
                                logger.debug(f"Discovered {len(pids)} PIDs for job {job_id} from {job_path}")
                                break
                    except (IOError, PermissionError):
                        pass

    return job_pids


def get_slurm_jobs_from_squeue():
    """Get jobs running on this node via squeue."""
    job_pids = {}
    short_hostname = hostname.split('.')[0]

    try:
        if SCONTROL_PATH:
            squeue_path = os.path.join(os.path.dirname(SCONTROL_PATH), "squeue")
        else:
            squeue_path = "squeue"

        result = subprocess.run(
            [squeue_path, "-w", short_hostname, "-h", "-o", "%A"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30
        )

        job_ids = [jid.strip() for jid in result.stdout.strip().split('\n') if jid.strip()]
        logger.debug(f"squeue reported {len(job_ids)} jobs on {short_hostname}")

        for job_id in job_ids:
            pids = get_pids_for_job(job_id)
            if pids:
                job_pids[job_id] = pids
            else:
                logger.debug(f"No PIDs found for job {job_id} from scontrol listpids")

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return job_pids


def get_pids_for_job(job_id):
    """Get all PIDs for a SLURM job using scontrol listpids."""
    pids = []

    if not SCONTROL_PATH:
        return pids

    try:
        result = subprocess.run(
            [SCONTROL_PATH, "listpids", str(job_id)],
            capture_output=True,
            text=True,
            timeout=10
        )

        for line in result.stdout.strip().split('\n')[1:]:
            parts = line.split()
            if parts:
                try:
                    pid = int(parts[0])
                    if pid > 0:
                        pids.append(pid)
                except ValueError:
                    continue

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    logger.debug(f"scontrol listpids found {len(pids)} PIDs for job {job_id}")
    return pids


def discover_job_pids():
    """Discover all SLURM job PIDs on this node."""
    job_pids = get_slurm_jobs_from_squeue()

    if not job_pids:
        logger.debug("No job PIDs found via squeue/listpids; trying cgroup fallback")
        job_pids = get_slurm_job_pids_from_cgroups()

    logger.debug(f"Discovered {len(job_pids)} SLURM jobs with local PIDs")
    return job_pids


# GPU Vendor Constants
GPU_VENDOR_CPU_ONLY = 0
GPU_VENDOR_NVIDIA = 1
GPU_VENDOR_AMD = 2
GPU_VENDOR_INTEL = 3

# System resources for percentage calculations
TOTAL_MEMORY = psutil.virtual_memory().total
CPU_COUNT = psutil.cpu_count()

# Track previous CPU times for rate calculation: {job_id: (cpu_seconds, timestamp)}
_prev_cpu_times = {}


def get_job_cpu_percent(job_id, current_cpu_seconds):
    """Calculate CPU utilization percentage based on delta from previous sample.

    Returns CPU% where 100% = 1 full CPU core utilized.
    Multi-core jobs can exceed 100% (e.g., 400% = 4 cores fully utilized).
    """
    global _prev_cpu_times

    current_time = time.time()
    cpu_percent = 0.0

    if job_id in _prev_cpu_times:
        prev_cpu, prev_time = _prev_cpu_times[job_id]
        time_delta = current_time - prev_time

        if time_delta > 0:
            cpu_delta = current_cpu_seconds - prev_cpu
            # CPU% = (cpu_seconds_used / elapsed_time) * 100
            cpu_percent = (cpu_delta / time_delta) * 100

    # Store current values for next calculation
    _prev_cpu_times[job_id] = (current_cpu_seconds, current_time)

    return round(cpu_percent, 1)


def get_memory_percent(mem_bytes):
    """Calculate memory utilization as percentage of total system memory."""
    if TOTAL_MEMORY > 0:
        return round((mem_bytes / TOTAL_MEMORY) * 100, 1)
    return 0.0


def get_process_cpu_seconds(pid):
    """Get cumulative CPU seconds for a process."""
    try:
        proc = psutil.Process(pid)
        cpu_times = proc.cpu_times()
        return cpu_times.user + cpu_times.system
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0


def get_process_memory_bytes(pid):
    """Get RSS memory in bytes for a process."""
    try:
        proc = psutil.Process(pid)
        return proc.memory_info().rss
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0


def cleanup_stale_jobs(active_job_ids):
    """Remove tracking data for jobs that are no longer running."""
    global _prev_cpu_times
    stale_jobs = set(_prev_cpu_times.keys()) - set(active_job_ids)
    for job_id in stale_jobs:
        del _prev_cpu_times[job_id]
    if stale_jobs:
        logger.debug(f"Cleaned up {len(stale_jobs)} stale job entries")


def get_gpu_metrics(handle, pid):
    """Get GPU metrics for a process. Returns (gpu_util, gpu_mem_util)."""
    gpu_util = 0
    gpu_mem_util = 0

    try:
        stats = pynvml.nvmlDeviceGetAccountingStats(handle, pid)
        meminfo = pynvml.nvmlDeviceGetMemoryInfo(handle)

        gpu_mem_util = max(
            round((stats.maxMemoryUsage / meminfo.total) * 100),
            stats.memoryUtilization
        )
        gpu_util = stats.gpuUtilization
    except pynvml.NVMLError:
        pass

    return gpu_util, gpu_mem_util


def write_utilization_to_db(job_id, gpu_idx, gpu_percent, gpu_mem_percent, cpu_percent, mem_bytes, mem_percent, gpu_vendor):
    """Write utilization metrics to database.

    Args:
        job_id: Slurm job ID
        gpu_idx: GPU index (-1 for CPU-only)
        gpu_percent: GPU utilization 0-100%
        gpu_mem_percent: GPU memory utilization 0-100%
        cpu_percent: CPU utilization % (can exceed 100% for multi-core)
        mem_bytes: Memory consumption in bytes
        mem_percent: Memory utilization as % of system memory (0-100%)
        gpu_vendor: GPU vendor code (0=CPU-only, 1=NVIDIA, 2=AMD, 3=Intel)
    """
    if job_id == "none" or not db_adapter:
        return

    try:
        timestamp = datetime.now().isoformat()
        db_adapter.execute("""
            INSERT INTO job_utilization
            (job_id, timestamp, hostname, gpu_index, gpu_vendor, gpu_util, gpu_mem_util, cpu_util, mem_util_bytes, mem_util_percent)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (job_id, timestamp, hostname, gpu_idx, gpu_vendor, gpu_percent, gpu_mem_percent, cpu_percent, mem_bytes, mem_percent))
        db_writes_total.labels(cluster_name=cluster_name, hostname=hostname).inc()
    except Exception as e:
        logger.debug(f"Failed to write utilization to database: {e}")
        db_write_errors_total.labels(cluster_name=cluster_name, hostname=hostname).inc()


def export_metrics_gpu():
    """Export metrics for NVIDIA GPU nodes."""
    try:
        device_count = pynvml.nvmlDeviceGetCount()
    except pynvml.NVMLError as e:
        logger.error(f"Failed to get GPU device count for job accounting: {e}")
        return

    # Track metrics per job
    # Structure: {job_id: {
    #   'gpus': {gpu_idx: (gpu_util, gpu_mem_util)},
    #   'pids_seen': set(),
    #   'cpu_seconds': 0,
    #   'mem_bytes': 0
    # }}
    job_metrics = {}

    for gpu_idx in range(device_count):
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_idx)
            processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
        except pynvml.NVMLError:
            continue

        logger.debug(f"GPU {gpu_idx} has {len(processes)} compute processes")

        for proc_info in processes:
            pid = proc_info.pid
            job_id = get_slurm_job_id_from_scontrol(pid)
            if job_id == "none":
                logger.debug(f"PID {pid} is not associated with a Slurm job")
                continue

            # Get GPU metrics
            gpu_util, gpu_mem_util = get_gpu_metrics(handle, pid)

            # Initialize job entry if needed
            if job_id not in job_metrics:
                job_metrics[job_id] = {
                    'gpus': {},
                    'pids_seen': set(),
                    'cpu_seconds': 0,
                    'mem_bytes': 0
                }

            # Store GPU metrics (one entry per GPU)
            if gpu_idx not in job_metrics[job_id]['gpus']:
                job_metrics[job_id]['gpus'][gpu_idx] = (gpu_util, gpu_mem_util)
            else:
                prev = job_metrics[job_id]['gpus'][gpu_idx]
                job_metrics[job_id]['gpus'][gpu_idx] = (
                    max(prev[0], gpu_util),
                    max(prev[1], gpu_mem_util)
                )

            # Count CPU/memory ONCE per PID (deduplicate across GPUs)
            if pid not in job_metrics[job_id]['pids_seen']:
                job_metrics[job_id]['pids_seen'].add(pid)
                job_metrics[job_id]['cpu_seconds'] += get_process_cpu_seconds(pid)
                job_metrics[job_id]['mem_bytes'] += get_process_memory_bytes(pid)

    for job_id, data in job_metrics.items():
        cpu_percent = get_job_cpu_percent(job_id, data['cpu_seconds'])
        total_mem_bytes = data['mem_bytes']
        mem_percent = get_memory_percent(total_mem_bytes)

        for gpu_idx, (gpu_util, gpu_mem_util) in data['gpus'].items():
            write_utilization_to_db(
                job_id, gpu_idx, gpu_util, gpu_mem_util,
                cpu_percent, total_mem_bytes, mem_percent, GPU_VENDOR_NVIDIA
            )

    job_pids = discover_job_pids()
    for job_id, pids in job_pids.items():
        if job_id in job_metrics:
            continue

        total_cpu_seconds = 0
        total_mem_bytes = 0
        for pid in pids:
            total_cpu_seconds += get_process_cpu_seconds(pid)
            total_mem_bytes += get_process_memory_bytes(pid)

        cpu_percent = get_job_cpu_percent(job_id, total_cpu_seconds)
        mem_percent = get_memory_percent(total_mem_bytes)
        write_utilization_to_db(
            job_id, -1, 0, 0,
            cpu_percent, total_mem_bytes, mem_percent, GPU_VENDOR_CPU_ONLY
        )

    cleanup_stale_jobs(set(job_metrics.keys()) | set(job_pids.keys()))


def export_metrics_cpu_only():
    """Export CPU/memory metrics for AMD/CPU-only nodes."""
    job_pids = discover_job_pids()

    if not job_pids:
        logger.debug("No SLURM jobs found on this node")
        cleanup_stale_jobs([])
        return

    total_pids = sum(len(pids) for pids in job_pids.values())
    logger.debug(f"Found {len(job_pids)} jobs with {total_pids} total PIDs")

    for job_id, pids in job_pids.items():
        # Aggregate metrics across all PIDs for this job
        total_cpu_seconds = 0
        total_mem_bytes = 0
        for pid in pids:
            total_cpu_seconds += get_process_cpu_seconds(pid)
            total_mem_bytes += get_process_memory_bytes(pid)

        # Calculate percentages
        cpu_percent = get_job_cpu_percent(job_id, total_cpu_seconds)
        mem_percent = get_memory_percent(total_mem_bytes)

        # Write one row per job (gpu_idx=-1 for CPU-only)
        write_utilization_to_db(job_id, -1, 0, 0, cpu_percent, total_mem_bytes, mem_percent, GPU_VENDOR_CPU_ONLY)

    # Cleanup tracking for jobs no longer running
    cleanup_stale_jobs(job_pids.keys())


def export_metrics():
    """Main metrics export function."""
    start_time = time.time()

    if CPU_ONLY_MODE:
        export_metrics_cpu_only()
    else:
        export_metrics_gpu()

    duration = time.time() - start_time
    collection_duration_seconds.labels(cluster_name=cluster_name, hostname=hostname).set(duration)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    cluster_name = get_cluster_name()
    logger.info(f"Cluster name: {cluster_name}")
    logger.info(f"Hostname: {hostname}")

    logger.info(f"Starting metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)

    if not CPU_ONLY_MODE and NVML_AVAILABLE:
        try:
            pynvml.nvmlInit()
            logger.info("NVML initialized successfully")
        except pynvml.NVMLError as e:
            logger.error(f"Failed to initialize NVML: {e}")
            logger.info("Falling back to CPU_ONLY_MODE")
            CPU_ONLY_MODE = True

    last_db_write = 0

    try:
        while True:
            try:
                current_time = time.time()
                if current_time - last_db_write >= DB_WRITE_INTERVAL:
                    export_metrics()
                    last_db_write = current_time
                    logger.debug("Wrote utilization samples to database")

            except Exception as e:
                logger.error(f"Error exporting metrics: {e}")

            time.sleep(SCRAPE_INTERVAL)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        signal_handler(None, None)
