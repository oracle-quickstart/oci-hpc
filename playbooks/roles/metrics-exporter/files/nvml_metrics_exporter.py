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
from prometheus_client import start_http_server, Gauge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
CPU_ONLY_MODE = os.getenv("CPU_ONLY_MODE", "false").lower() == "true"
SCONTROL_PATH = os.getenv("SCONTROL_PATH")
METRICS_PORT = int(os.getenv("METRICS_PORT", "9800"))
SCRAPE_INTERVAL = int(os.getenv("SCRAPE_INTERVAL", "15"))

# Global state
cluster_name = "none"
hostname = socket.gethostname()

# Conditional NVML import
if not CPU_ONLY_MODE:
    try:
        import pynvml
        NVML_AVAILABLE = True
    except ImportError:
        logger.warning("pynvml not available, falling back to CPU_ONLY_MODE")
        CPU_ONLY_MODE = True
        NVML_AVAILABLE = False
else:
    NVML_AVAILABLE = False

logger.info(f"SCONTROL_PATH: {SCONTROL_PATH}")
logger.info(f"CPU_ONLY_MODE: {CPU_ONLY_MODE}")
logger.info(f"METRICS_PORT: {METRICS_PORT}")
logger.info(f"SCRAPE_INTERVAL: {SCRAPE_INTERVAL}s")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Shutting down...")
    if NVML_AVAILABLE and not CPU_ONLY_MODE:
        try:
            pynvml.nvmlShutdown()
        except Exception as e:
            logger.debug(f"Error during NVML shutdown: {e}")
    sys.exit(0)


# CPU/Memory metrics (always available)
slurm_job_cpu_util_seconds = Gauge(
    "slurm_job_cpu_util_seconds",
    "CPU utilization in seconds (user + system time)",
    ["cluster_name", "hostname", "slurm_job_pid", "slurm_job_id"]
)

slurm_job_mem_util_bytes = Gauge(
    "slurm_job_mem_util_bytes",
    "Memory utilization in bytes (RSS)",
    ["cluster_name", "hostname", "slurm_job_pid", "slurm_job_id"]
)

# GPU metrics (only defined when not in CPU-only mode)
if not CPU_ONLY_MODE:
    slurm_job_gpu_util_percent = Gauge(
        "slurm_job_gpu_util_percent",
        "GPU Compute utilization in percent",
        ["cluster_name", "hostname", "gpu", "slurm_job_pid", "slurm_job_id"]
    )

    slurm_job_gpu_mem_util_percent = Gauge(
        "slurm_job_gpu_mem_util_percent",
        "GPU Memory utilization in percent",
        ["cluster_name", "hostname", "gpu", "slurm_job_pid", "slurm_job_id"]
    )

    available_gpu_count = Gauge(
        "available_gpu_count",
        "Available GPU count",
        ["cluster_name", "hostname"]
    )


def get_cluster_name():
    """Extract cluster name from SLURM node features or metadata."""
    cluster = "none"
    try:
        # Use short hostname (SLURM typically uses short names)
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
                    # Parse "CN__complete-filly" -> "complete-filly"
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
            logger.error("SCONTROL_PATH not set")
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
    except subprocess.CalledProcessError as e:
        logger.debug(f"Error running scontrol pidinfo for PID {pid}: {e}")
        return "none"
    except subprocess.TimeoutExpired:
        logger.error(f"scontrol pidinfo timed out for PID {pid}")
        return "none"


def get_slurm_job_pids_from_cgroups():
    """
    Discover SLURM job PIDs from cgroup filesystem.
    Works with both cgroup v1 and v2.
    """
    job_pids = {}  # {job_id: [pids]}
    
    # Patterns for different cgroup configurations
    cgroup_patterns = [
        # cgroup v2 patterns
        "/sys/fs/cgroup/system.slice/slurmstepd.scope/job_*/",
        "/sys/fs/cgroup/system.slice/slurmstepd.scope/job_*/step_*/",
        # cgroup v1 patterns (various controllers)
        "/sys/fs/cgroup/memory/slurm/uid_*/job_*/",
        "/sys/fs/cgroup/cpuacct/slurm/uid_*/job_*/",
        "/sys/fs/cgroup/cpu,cpuacct/slurm/uid_*/job_*/",
        "/sys/fs/cgroup/freezer/slurm/uid_*/job_*/",
        # Alternative layouts
        "/sys/fs/cgroup/*/slurm_*/job_*/",
    ]
    
    for pattern in cgroup_patterns:
        for job_path in glob.glob(pattern):
            # Extract job ID from path
            job_id_match = re.search(r'job_(\d+)', job_path)
            if not job_id_match:
                continue
            job_id = job_id_match.group(1)
            
            # Skip if we already have PIDs for this job
            if job_id in job_pids:
                continue
            
            # Try to read PIDs from cgroup.procs (v2) or tasks (v1)
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
                                logger.debug(f"Found {len(pids)} PIDs for job {job_id} via cgroups")
                                break
                    except (IOError, PermissionError) as e:
                        logger.debug(f"Error reading {procs_path}: {e}")
    
    return job_pids


def get_slurm_jobs_from_squeue():
    """
    Fallback method: get jobs running on this node via squeue.
    Used when cgroup discovery fails.
    """
    job_pids = {}
    short_hostname = hostname.split('.')[0]
    
    try:
        # Determine squeue path
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
        print(job_ids)
        for job_id in job_ids:
            pids = get_pids_for_job(job_id)
            if pids:
                job_pids[job_id] = pids
                logger.debug(f"Found {len(pids)} PIDs for job {job_id} via squeue")
                
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running squeue: {e}")
    except subprocess.TimeoutExpired:
        logger.error("squeue command timed out")
    except FileNotFoundError:
        logger.error(f"squeue not found at {squeue_path}")
    
    return job_pids


def get_pids_for_job(job_id):
    """Get all PIDs associated with a SLURM job using scontrol listpids."""
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
        
        # Skip header line, parse PID from first column
        for line in result.stdout.strip().split('\n')[1:]:
          
            parts = line.split()
            if parts:
                try:
                    pid = int(parts[0])
                    if pid > 0:  # Skip -1 and any invalid PIDs
                        pids.append(pid)
                except ValueError:
                    continue
                    
    except subprocess.CalledProcessError as e:
        logger.debug(f"Error running scontrol listpids for job {job_id}: {e}")
    except subprocess.TimeoutExpired:
        logger.error(f"scontrol listpids timed out for job {job_id}")
    
    return pids


def discover_job_pids():
    """
    Discover all SLURM job PIDs on this node.
    Tries cgroups first, falls back to squeue.
    """
    job_pids = get_slurm_jobs_from_squeue()
    print(job_pids)
    
    if not job_pids:
        logger.debug("No jobs found via squeue, trying cgroups fallback")
        job_pids = get_slurm_job_pids_from_cgroups()
    
    return job_pids


def export_process_cpu_and_memory(pid, job_id):
    """Export CPU and memory metrics for a process."""
    cpu_total = 0
    rss = 0
    
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        logger.debug(f"Process with PID {pid} no longer exists")
        return
    except psutil.AccessDenied:
        logger.debug(f"Access denied for PID {pid}")
        return

    try:
        cpu_times = proc.cpu_times()
        cpu_total = cpu_times.user + cpu_times.system
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.debug(f"Error fetching CPU times for PID {pid}: {e}")

    try:
        mem_info = proc.memory_info()
        rss = mem_info.rss
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        logger.debug(f"Error fetching memory info for PID {pid}: {e}")

    slurm_job_cpu_util_seconds.labels(
        cluster_name=cluster_name,
        hostname=hostname,
        slurm_job_id=job_id,
        slurm_job_pid=pid
    ).set(cpu_total)
    
    slurm_job_mem_util_bytes.labels(
        cluster_name=cluster_name,
        hostname=hostname,
        slurm_job_id=job_id,
        slurm_job_pid=pid
    ).set(rss)


def export_gpu_utilization(handle, pid, gpu_idx, job_id):
    """Export GPU utilization metrics for a process (NVIDIA only)."""
    try:
        stats = pynvml.nvmlDeviceGetAccountingStats(handle, pid)
        meminfo = pynvml.nvmlDeviceGetMemoryInfo(handle)
        
        # Calculate memory utilization percentage
        process_mem_usage = max(
            round((stats.maxMemoryUsage / meminfo.total) * 100),
            stats.memoryUtilization
        )
        
        slurm_job_gpu_util_percent.labels(
            cluster_name=cluster_name,
            hostname=hostname,
            gpu=gpu_idx,
            slurm_job_id=job_id,
            slurm_job_pid=pid
        ).set(stats.gpuUtilization)
        
        slurm_job_gpu_mem_util_percent.labels(
            cluster_name=cluster_name,
            hostname=hostname,
            gpu=gpu_idx,
            slurm_job_id=job_id,
            slurm_job_pid=pid
        ).set(process_mem_usage)
        
    except pynvml.NVMLError as e:
        logger.debug(f"Failed to get accounting stats for PID {pid} on GPU {gpu_idx}: {e}")


def export_metrics_gpu():
    """Export metrics for NVIDIA GPU nodes."""
    try:
        device_count = pynvml.nvmlDeviceGetCount()
        available_gpu_count.labels(
            cluster_name=cluster_name,
            hostname=hostname
        ).set(device_count)
    except pynvml.NVMLError as e:
        logger.error(f"Failed to get GPU device count: {e}")
        return

    for gpu_idx in range(device_count):
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_idx)
        except pynvml.NVMLError as e:
            logger.error(f"Failed to get handle for GPU {gpu_idx}: {e}")
            continue

        try:
            processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
        except pynvml.NVMLError as e:
            logger.debug(f"Failed to get processes for GPU {gpu_idx}: {e}")
            processes = []

        logger.debug(f"GPU {gpu_idx} has {len(processes)} processes running")

        for proc_info in processes:
            pid = proc_info.pid
            job_id = get_slurm_job_id_from_scontrol(pid)
            logger.debug(f"Found job {job_id} running on GPU {gpu_idx}")
            export_process_cpu_and_memory(pid, job_id)
            export_gpu_utilization(handle, pid, gpu_idx, job_id)


def export_metrics_cpu_only():
    """Export CPU/memory metrics for AMD/CPU-only nodes."""
    job_pids = discover_job_pids()
    
    if not job_pids:
        logger.debug("No SLURM jobs found on this node")
        return
    
    total_pids = sum(len(pids) for pids in job_pids.values())
    logger.debug(f"Found {len(job_pids)} jobs with {total_pids} total PIDs")
    
    for job_id, pids in job_pids.items():
        for pid in pids:
            export_process_cpu_and_memory(pid, job_id)


def export_metrics():
    """Main metrics export function - routes to appropriate handler."""
    if CPU_ONLY_MODE:
        export_metrics_cpu_only()
    else:
        export_metrics_gpu()


if __name__ == '__main__':
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize cluster info
    cluster_name = get_cluster_name()
    logger.info(f"Cluster name: {cluster_name}")
    logger.info(f"Hostname: {hostname}")
    
    # Start Prometheus HTTP server
    logger.info(f"Starting metrics server on port {METRICS_PORT}")
    start_http_server(METRICS_PORT)
    
    # Initialize NVML if needed
    if not CPU_ONLY_MODE and NVML_AVAILABLE:
        try:
            pynvml.nvmlInit()
            logger.info("NVML initialized successfully")
        except pynvml.NVMLError as e:
            logger.error(f"Failed to initialize NVML: {e}")
            logger.info("Falling back to CPU_ONLY_MODE")
            CPU_ONLY_MODE = True
    
    # Main metrics collection loop
    try:
        while True:
            try:
                export_metrics()
            except Exception as e:
                logger.error(f"Error exporting metrics: {e}")
            time.sleep(SCRAPE_INTERVAL)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        signal_handler(None, None)
