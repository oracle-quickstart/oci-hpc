import os
import time
import socket
import pynvml
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
cluster_name = "none"

def signal_handler(signum, frame):
    logger.info("Shutting down NVML...")
    pynvml.nvmlShutdown()
    sys.exit(0)

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

slurm_job_cpu_util_seconds = Gauge(
    "slurm_job_cpu_util_seconds",
    "CPU utilization in seconds",
    ["cluster_name", "hostname", "slurm_job_pid", "slurm_job_id"]
)

slurm_job_mem_util_bytes = Gauge(
    "slurm_job_mem_util_bytes",
    "GPU Memory utilization in bytes",
    ["cluster_name", "hostname", "slurm_job_pid", "slurm_job_id"]
)

nccl_profiler_group_latency_nanoseconds = Gauge(
    "nccl_profiler_group_latency_nanoseconds", 
    "NCCL Profiler latency measurement for each group event in nano seconds", 
    ["cluster_name", "hostname", "nccl_event_id", "slurm_job_pid", "slurm_job_id"]
)

def get_cluster_name():
    cluster_name = "none"
    try:
        gpu_host = platform.node()
        scontrol_output = subprocess.check_output(["scontrol", "show", f"node={gpu_host}", "-o", "--json"], universal_newlines=True)
        slurm_node_features = json.loads(scontrol_output)
        cluster_name = slurm_node_features['nodes'][0]['features'][1].split("__")[1]
    except subprocess.CalledProcessError as e:
        logger.error(f"An error occurred: {e}")
    return cluster_name.strip()


def get_slurm_job_id_from_scontrol(pid):
    try:
        result = subprocess.run(
            ["scontrol", "pidinfo", str(pid)],
            capture_output=True,
            text=True,
            check=True
        )
        output = result.stdout.strip()
        match = re.search(r"Slurm JobId=(\d+)", output)
        if match:
            job_id = match.group(1)
            return job_id
        else:
            return "none"
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running scontrol pidinfo: {e}")
        return "none"


def export_nccl_profiler_trace(cluster_name, hostname):
    existing_files = glob.glob('/tmp/nccl-profiler-output-*')
    for filepath in existing_files:
        if not filepath.endswith(".processed"):            
            logger.info(f"Processing file: {filepath}")
            group_begins = {}
            try:
                with open(filepath, 'r') as f:
                    events = json.load(f)
            except Exception as e:
                logger.error(f"Error reading file {filepath}: {e}")
            for event in events:
                if event.get("name") == "Group":
                    event_id = event.get("id")
                    pid = event.get("pid")
                    job_id = get_slurm_job_id_from_scontrol(pid)
                    phase = event.get("ph")
                    ts = event.get("ts")
                    key = (event_id, pid)                
                    if phase == "b":
                        group_begins[key] = ts
                    elif phase == "e":
                        if key in group_begins:
                            start_ts = group_begins.pop(key)
                            latency_micro = ts - start_ts  # latency in microseconds
                            latency_ns = latency_micro * 1000  # convert to nanoseconds
                            nccl_profiler_group_latency_nanoseconds.labels(cluster_name=cluster_name, hostname=hostname, nccl_event_id=str(event_id), slurm_job_pid=str(pid), slurm_job_id=str(job_id)).set(latency_ns)
                            logger.info(f"Computed latency for Group {event_id} with pid {pid}: {latency_ns:.6f} nanoseconds")
                        else:
                            logger.info(f"Warning: End event for Group {event_id} (pid {pid}) without a matching begin event.")
            new_filepath = filepath + ".processed"
            try:
                os.rename(filepath, new_filepath)
                logger.info(f"Renamed file {filepath} to {new_filepath}")
            except Exception as e:
                logger.error(f"Error renaming file {filepath} to {new_filepath}: {e}")


def export_process_cpu_and_memory(pid, hostname, job_id):
    cpu_total = 0
    rss = 0
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        logger.debug(f"Process with PID {pid} not found.")

    try:
        cpu_times = proc.cpu_times()
        cpu_total = cpu_times.user + cpu_times.system
    except Exception as e:
        logger.error(f"Error fetching CPU times for PID {pid}: {e}")

    try:
        mem_info = proc.memory_info()
        rss = mem_info.rss
    except Exception as e:
        logger.error(f"Error fetching memory info for PID {pid}: {e}")
    
    slurm_job_cpu_util_seconds.labels(cluster_name=cluster_name, hostname=hostname, slurm_job_id=job_id, slurm_job_pid=pid).set(cpu_total)
    slurm_job_mem_util_bytes.labels(cluster_name=cluster_name, hostname=hostname, slurm_job_id=job_id, slurm_job_pid=pid).set(rss)

def export_gpu_utilization(handle, pid, hostname, gpu_idx, job_id):
    try:
        stats = pynvml.nvmlDeviceGetAccountingStats(handle, pid)
        meminfo = pynvml.nvmlDeviceGetMemoryInfo(handle)
        processMemUsage = max(round((stats.maxMemoryUsage/meminfo.total)*100), stats.memoryUtilization)        
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
        ).set(processMemUsage)
    except pynvml.NVMLError as e:
        logger.error(f"Failed to get accounting stats for PID {pid} on GPU {gpu_idx}: {e}")

def export_metrics():    
    export_nccl_profiler_trace(cluster_name, hostname)
    try:
        device_count = pynvml.nvmlDeviceGetCount()
    except pynvml.NVMLError as e:
        logger.error(f"Failed to get device count: {e}")
        return

    for gpu_idx in range(device_count):
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_idx)
        except pynvml.NVMLError as e:
            logger.error(f"Failed to get handle for GPU {gpu_idx}: {e}")
            continue

        try:
            processes = pynvml.nvmlDeviceGetComputeRunningProcesses(handle)
        except pynvml.NVMLError:
            logger.error(f"Failed to get processes for GPU {gpu_idx}")
            processes = []    
        
        logger.debug(f"GPU {gpu_idx} has {len(processes)} processes running")

        for proc_info in processes:
            pid = proc_info.pid
            job_id = get_slurm_job_id_from_scontrol(pid)
            logger.debug(f"Found job {job_id} running on GPU {gpu_idx}")
            export_process_cpu_and_memory(pid, hostname, job_id)
            export_gpu_utilization(handle, pid, hostname, gpu_idx, job_id)

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)    
    cluster_name = get_cluster_name()
    hostname = socket.gethostname()
    start_http_server(9800)
    pynvml.nvmlInit()
    try:
        while True:
            export_metrics()
            time.sleep(15)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        signal_handler(None, None)

