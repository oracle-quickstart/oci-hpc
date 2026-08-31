#!/usr/bin/env python3
"""
Slurm REST API Exporter

Collects metrics from slurmrestd and exports to Prometheus.
Supports API versions v0.0.40 - v0.0.44 (Slurm 23.02 - 25.11).

Usage:
    python slurm_rest_exporter.py --url http://slurmrestd:6820 --port 9901 --interval 60
    python slurm_rest_exporter.py --url http://slurmrestd:6820 --test
    python slurm_rest_exporter.py --url http://slurmrestd:6820 --once

Environment:
    SLURMRESTD_URL      - API URL (default: http://localhost:6820)
    SLURM_JWT           - JWT token for authentication
    SLURM_USER          - Username for auth (fallback, default: root)
"""

import argparse
import logging
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ClusterShell.NodeSet import NodeSet
from prometheus_client import Gauge, start_http_server
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('slurm_rest_exporter')


def expand_hostlist(hostlist: str) -> List[str]:
    """Expand Slurm hostlist notation to individual node names."""
    if not hostlist:
        return []
    return list(NodeSet(hostlist))


# =============================================================================
# sinfo helpers for per-node state metric
# =============================================================================

def _base_state(state: str) -> str:
    """Normalize Slurm state but preserve '~', '*', '$' suffixes."""
    state = (state or "").strip().upper()
    match = re.match(r"([A-Z]+)([~*$]?)", state)
    if match:
        base, suffix = match.groups()
        return base + suffix
    return state or "UNKNOWN"


def _parse_gpu_details(gres: str) -> tuple:
    """Parse GPU count and vendor from GRES string."""
    match = re.search(r"gpu:(?:[^:,]*:)?(\d+)", gres or "", re.IGNORECASE)
    gpu_count = int(match.group(1)) if match else 0
    if gpu_count == 0:
        return 0, "none"
    if re.search(r"gpu:[^,]*(amd|mi\d)", gres or "", re.IGNORECASE):
        return gpu_count, "amd"
    return gpu_count, "nvidia"


def _parse_alloc_total(cpu_load: str) -> tuple:
    """Parse sinfo '%C' (alloc/idle/other/total) into (alloc, total)."""
    parts = (cpu_load or "").split("/")
    alloc = parts[0] if len(parts) > 0 and parts[0] else "0"
    total = parts[-1] if len(parts) > 0 and parts[-1] else "0"
    return alloc, total


# =============================================================================
# Version Adapter - handles API differences between Slurm versions
# =============================================================================

class VersionAdapter:
    """Normalizes data across API versions v0.0.40 - v0.0.44."""

    @staticmethod
    def get_value(field: Any, default: Any = 0) -> Any:
        """Extract value from dict format: {"set": true, "number": 123} or list."""
        if field is None:
            return default
        if isinstance(field, dict):
            if field.get("infinite"):
                return float("inf")
            if "set" in field and not field.get("set"):
                return default
            return field.get("number", field.get("count", default))
        if isinstance(field, list):
            # Return first element if list, or default if empty
            return field[0] if field else default
        return field

    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        """Safely convert value to int, handling lists, dicts, etc."""
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return default
        if isinstance(value, list):
            return int(value[0]) if value else default
        if isinstance(value, dict):
            v = value.get("number", value.get("count", default))
            return int(v) if v is not None else default
        return default

    @staticmethod
    def get_timestamp(field: Any) -> Optional[datetime]:
        """Parse timestamp from various formats."""
        if field is None:
            return None
        if isinstance(field, dict):
            ts = field.get("number", 0)
            return datetime.fromtimestamp(ts) if ts > 0 else None
        if isinstance(field, (int, float)) and field > 0:
            return datetime.fromtimestamp(field)
        if isinstance(field, str):
            for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S']:
                try:
                    return datetime.strptime(field, fmt)
                except ValueError:
                    pass
        return None

    @staticmethod
    def get_state(field: Any) -> str:
        """Extract state from string, list, or dict."""
        if field is None:
            return "UNKNOWN"
        if isinstance(field, str):
            return field.split()[0].upper()
        if isinstance(field, list):
            return field[0].upper() if field else "UNKNOWN"
        if isinstance(field, dict):
            current = field.get("current", [])
            if isinstance(current, list) and current:
                return current[0].upper()
        return "UNKNOWN"

    @staticmethod
    def get_tres_count(tres: Any, tres_type: str) -> int:
        """Extract TRES count (e.g., 'gres/gpu') from string or list."""
        if not tres:
            return 0
        if isinstance(tres, str):
            for part in tres.split(","):
                if "=" in part and tres_type in part:
                    val = part.split("=")[1].split(":")[0]
                    digits = ''.join(c for c in val if c.isdigit())
                    return int(digits) if digits else 0
        if isinstance(tres, list):
            for t in tres:
                if isinstance(t, dict):
                    name = t.get("type", "")
                    if t.get("name"):
                        name = f"{name}/{t['name']}"
                    if tres_type in name:
                        return VersionAdapter.get_value(t.get("count"), 0)
        return 0

    @staticmethod
    def parse_tres_list(tres_list: List) -> Dict[str, int]:
        """Parse TRES list to dict: {'cpu': 8, 'gres/gpu': 2, ...}."""
        result = {}
        if not isinstance(tres_list, list):
            return result
        for t in tres_list:
            if isinstance(t, dict):
                label = t.get("type", "")
                if t.get("name"):
                    label = f"{label}/{t['name']}"
                result[label] = VersionAdapter.get_value(t.get("count"), 0)
        return result

    @staticmethod
    def parse_tres_with_stats(tres_dict: Dict) -> Dict:
        """Parse full TRES structure with requested/consumed/allocated stats.

        Returns: {
            'requested': {'total': {...}, 'average': {...}, ...},
            'consumed': {'total': {...}, 'average': {...}, ...},
            'allocated': {'cpu': 8, 'gres/gpu': 2, ...}
        }
        """
        result = {'requested': {}, 'consumed': {}, 'allocated': {}}
        if not isinstance(tres_dict, dict):
            return result

        # Parse allocated (simple list)
        if 'allocated' in tres_dict:
            result['allocated'] = VersionAdapter.parse_tres_list(tres_dict['allocated'])

        # Parse requested/consumed with stats (total, average, max, min)
        for stat_type in ['requested', 'consumed']:
            if stat_type in tres_dict and isinstance(tres_dict[stat_type], dict):
                for stat_name, stat_list in tres_dict[stat_type].items():
                    result[stat_type][stat_name] = VersionAdapter.parse_tres_list(stat_list)

        return result

    def parse_job_step(self, step: Dict) -> Dict:
        """Parse a job step to normalized format."""
        gv = self.get_value

        step_info = step.get("step", {})
        time_data = step.get("time", {})
        nodes_data = step.get("nodes", {})
        tres_data = step.get("tres", {})

        # Parse TRES with full stats
        tres = self.parse_tres_with_stats(tres_data)

        # Calculate utilization if available
        elapsed = gv(time_data.get("elapsed"), 0)
        alloc_cpus = tres['allocated'].get('cpu', 0)
        alloc_gpus = tres['allocated'].get('gres/gpu', 0)

        cpu_util = 0.0
        gpu_util = 0.0

        if elapsed > 0 and alloc_cpus > 0:
            # CPU utilization: total CPU time used / max possible
            total_cpu_time = tres['requested'].get('total', {}).get('cpu', 0)
            max_cpu_time = elapsed * 1000 * alloc_cpus  # milliseconds
            if max_cpu_time > 0:
                cpu_util = total_cpu_time / max_cpu_time

        if alloc_gpus > 0:
            # GPU utilization from gres/gpuutil if available
            gpu_util_total = tres['requested'].get('total', {}).get('gres/gpuutil', 0)
            if gpu_util_total > 0:
                gpu_util = (gpu_util_total / 100.0) / alloc_gpus

        return {
            "step_id": gv(step_info.get("id"), 0),
            "step_name": step_info.get("name", ""),
            "elapsed_seconds": elapsed,
            "node_count": gv(nodes_data.get("count"), 0),
            "alloc_cpus": alloc_cpus,
            "alloc_gpus": alloc_gpus,
            "cpu_utilization": cpu_util,
            "gpu_utilization": gpu_util,
            "tres": tres,
        }

    def parse_job(self, job: Dict) -> Dict:
        """Parse job to normalized format."""
        gv = self.get_value

        # TRES from allocated or string
        tres = job.get("tres", {})
        tres_alloc = tres.get("allocated", []) if isinstance(tres, dict) else []
        tres_alloc_str = job.get("tres_alloc_str", "")

        num_gpus = (self.get_tres_count(tres_alloc, "gres/gpu") or
                    self.get_tres_count(tres_alloc_str, "gres/gpu"))
        num_cpus_tres = (self.get_tres_count(tres_alloc, "cpu") or
                         self.get_tres_count(tres_alloc_str, "cpu"))
        num_nodes_tres = (self.get_tres_count(tres_alloc, "node") or
                          self.get_tres_count(tres_alloc_str, "node"))

        # Time
        time_data = job.get("time", {})
        submit = self.get_timestamp(time_data.get("submission", job.get("submit_time")))
        start = self.get_timestamp(time_data.get("start", job.get("start_time")))
        end = self.get_timestamp(time_data.get("end", job.get("end_time")))
        elapsed = gv(time_data.get("elapsed", job.get("elapsed", 0)), 0)

        wait = 0
        if submit and start:
            wait = max(0, int((start - submit).total_seconds()))

        # Nodes - try multiple sources
        nodes = job.get("node_count", 0)
        if isinstance(nodes, dict):
            nodes = gv(nodes, 0)
        if not nodes:
            nodes = num_nodes_tres

        # CPUs - try multiple sources
        cpus = gv(job.get("cpus"), 0)
        if not cpus:
            cpus = num_cpus_tres

        # Job resources for partition metrics - handle both v0040 and later formats
        job_resources = job.get("job_resources") or {}
        alloc_cpus = 0
        alloc_nodes = 0

        # v0040 format: allocated_cores/allocated_cpus/allocated_hosts
        if job_resources and ("allocated_cores" in job_resources or "allocated_cpus" in job_resources):
            alloc_cpus = job_resources.get("allocated_cores") or job_resources.get("allocated_cpus", 0)
            alloc_nodes = job_resources.get("allocated_hosts", 0)
        # > v0040 format: nodes.allocation[].cpus.used, nodes.count
        elif job_resources and "nodes" in job_resources and isinstance(job_resources.get("nodes"), dict):
            nodes_data = job_resources["nodes"]
            alloc_nodes = self.get_value(nodes_data.get("count"), 0)
            allocations = nodes_data.get("allocation", [])
            if isinstance(allocations, list):
                for alloc in allocations:
                    if isinstance(alloc, dict):
                        cpus_data = alloc.get("cpus", {})
                        if isinstance(cpus_data, dict):
                            alloc_cpus += self.get_value(cpus_data.get("used"), 0)
                        else:
                            alloc_cpus += self.get_value(cpus_data, 0)

        # Exit code
        exit_code = job.get("exit_code", 0)
        if isinstance(exit_code, dict):
            exit_code = gv(exit_code.get("status", exit_code), 0)

        account = job.get("account") or ""
        parts = account.split("/") if account else [""]

        # Parse job steps if available (from slurmdbd)
        steps = []
        steps_data = job.get("steps", [])
        if isinstance(steps_data, list):
            for step in steps_data:
                step_name = step.get("step", {}).get("name", "")
                # Skip batch and extern steps for productivity calc
                if step_name not in ("batch", "extern"):
                    steps.append(self.parse_job_step(step))

        # Calculate job productivity from steps
        productivity = 0.0
        if steps and elapsed > 0:
            step_utils = []
            for s in steps:
                util = max(s["cpu_utilization"], s["gpu_utilization"])
                step_utils.append(util * s["elapsed_seconds"])
            if step_utils:
                productivity = sum(step_utils) / elapsed

        si = self.safe_int
        # Get node list for running jobs (for unique node counting)
        node_list = expand_hostlist(job.get("nodes", ""))

        return {
            "job_id": job.get("job_id", 0),
            "name": job.get("name", job.get("job_name", "")),
            "user": job.get("user", job.get("user_name", "")),
            "account": account,
            "account_l1": parts[0] if len(parts) >= 1 else "",
            "account_l2": parts[1] if len(parts) >= 2 else "",
            "account_l3": parts[2] if len(parts) >= 3 else "",
            "partition": job.get("partition", ""),
            "cluster": job.get("cluster", ""),
            "qos": job.get("qos", ""),
            "state": self.get_state(job.get("job_state", job.get("state"))),
            "exit_code": si(exit_code, 0),
            "num_nodes": si(nodes, 0) or si(alloc_nodes, 0),
            "num_cpus": si(cpus, 0) or si(alloc_cpus, 0),
            "num_gpus": si(num_gpus, 0),
            "alloc_cpus": si(alloc_cpus, 0),
            "alloc_nodes": si(alloc_nodes, 0),
            "node_list": node_list,
            "submit_time": submit,
            "start_time": start,
            "end_time": end,
            "elapsed_seconds": si(elapsed, 0),
            "wait_seconds": wait,
            "priority": gv(job.get("priority"), 0),
            "gres_detail": job.get("gres_detail", []),
            "steps": steps,
            "productivity": productivity,
        }

    def parse_node(self, node: Dict) -> Dict:
        """Parse node to normalized format."""
        gv = self.get_value

        # State
        states = node.get("state") or []
        if isinstance(states, str):
            states = [states]
        elif not isinstance(states, list):
            states = []
        states = [s.upper() for s in states if s]
        state = self._primary_state(states)

        # GPUs from GRES
        gres = node.get("gres", "")
        total_gpus = self._parse_gres(gres, "gpu")
        alloc_gpus = self._parse_gres(node.get("gres_used", ""), "gpu")

        # Partitions
        partitions = node.get("partitions") or []
        if isinstance(partitions, str):
            partitions = [partitions] if partitions else []
        elif not isinstance(partitions, list):
            partitions = []

        # Idle resources
        idle_cpus = node.get("cpus", 0) - node.get("alloc_cpus", 0)
        idle_gpus = total_gpus - alloc_gpus

        return {
            "name": node.get("name", ""),
            "state": state,
            "states": states,
            "cpus": node.get("cpus", 0),
            "alloc_cpus": node.get("alloc_cpus", 0),
            "idle_cpus": max(0, idle_cpus),
            "effective_cpus": node.get("effective_cpus", node.get("cpus", 0)),
            "memory": gv(node.get("real_memory"), 0),
            "alloc_memory": gv(node.get("alloc_memory"), 0),
            "total_gpus": total_gpus,
            "alloc_gpus": alloc_gpus,
            "idle_gpus": max(0, idle_gpus),
            "partitions": partitions,
            "reservation": node.get("reservation", ""),
            "reason": node.get("reason", ""),
        }

    def parse_reservation(self, res: Dict) -> Dict:
        """Parse reservation to normalized format."""
        gv = self.get_value

        # TRES parsing for CPUs
        tres = res.get("tres", "")
        tres_cpus = 0
        if isinstance(tres, str) and "=" in tres:
            try:
                tres_cpus = int(tres.split("=")[1].split(",")[0])
            except (ValueError, IndexError):
                pass
        elif isinstance(tres, dict):
            tres_cpus = gv(tres.get("count"), 0)

        return {
            "name": res.get("name", ""),
            "node_count": gv(res.get("node_count"), 0),
            "core_count": gv(res.get("core_count"), 0),
            "cpus": tres_cpus,
            "start_time": gv(res.get("start_time"), 0),
            "end_time": gv(res.get("end_time"), 0),
            "state": res.get("state", ""),
        }

    def _primary_state(self, states: List[str]) -> str:
        """Get primary state from list."""
        for check, canon in [("DOWN", "DOWN"), ("DRAIN", "DRAIN"), ("MAINT", "MAINT"),
                             ("MIXED", "MIXED"), ("ALLOCATED", "ALLOCATED"), ("IDLE", "IDLE")]:
            if any(check in s for s in states):
                return canon
        return states[0] if states else "UNKNOWN"

    def _parse_gres(self, gres: str, gres_type: str) -> int:
        """Parse 'gpu:a100:4' format."""
        if not gres:
            return 0
        total = 0
        for part in str(gres).split(","):
            if gres_type not in part:
                continue
            part = part.split("(")[0]
            for seg in reversed(part.split(":")):
                try:
                    total += int(seg)
                    break
                except ValueError:
                    pass
        return total


# =============================================================================
# REST Client
# =============================================================================

class SlurmRestClient:
    """Slurm REST API client with auto version detection."""

    VERSIONS = ["v0.0.44", "v0.0.43", "v0.0.42", "v0.0.41", "v0.0.40"]

    def __init__(self, url: str, token: str = None, user: str = None,
                 version: str = None, timeout: int = 30):
        self.url = url.rstrip('/')
        self.token = token or os.environ.get('SLURM_JWT')
        self.user = user or os.environ.get('SLURM_USER', 'root')
        self.version = version
        self.timeout = timeout
        self.session = requests.Session()
        self.adapter = VersionAdapter()
        self._setup_headers()

    def _setup_headers(self):
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.token:
            headers['X-SLURM-USER-TOKEN'] = self.token
        else:
            headers['X-SLURM-USER-NAME'] = self.user
        self.session.headers.update(headers)

    def detect_version(self) -> str:
        """Auto-detect API version."""
        if self.version:
            return self.version
        for ver in self.VERSIONS:
            try:
                resp = self.session.get(f"{self.url}/slurm/{ver}/ping", timeout=5)
                if resp.status_code == 200:
                    self.version = ver
                    logger.info(f"Detected API version: {ver}")
                    return ver
            except Exception:
                pass
        self.version = "v0.0.43"
        logger.warning(f"Version detection failed, using {self.version}")
        return self.version

    def _get(self, endpoint: str, params: Dict = None) -> Dict:
        url = f"{self.url}{endpoint}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    @property
    def ver(self) -> str:
        return self.version or "v0.0.43"

    def get_jobs(self) -> List[Dict]:
        """Get current jobs from slurmctld."""
        data = self._get(f"/slurm/{self.ver}/jobs")
        return [self.adapter.parse_job(j) for j in data.get("jobs", [])]

    def get_db_jobs(self, hours: int = 24) -> List[Dict]:
        """Get historical jobs from slurmdbd."""
        start = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
        data = self._get(f"/slurmdb/{self.ver}/jobs", {"start_time": start})
        return [self.adapter.parse_job(j) for j in data.get("jobs", [])]

    def get_job(self, job_id: int) -> Optional[Dict]:
        """Get single job with full details from slurmdbd (includes steps and TRES stats)."""
        try:
            data = self._get(f"/slurmdb/{self.ver}/job/{job_id}")
            jobs = data.get("jobs", [])
            if jobs:
                return self.adapter.parse_job(jobs[0])
        except Exception as e:
            logger.warning(f"Failed to get job {job_id}: {e}")
        return None

    def get_nodes(self) -> List[Dict]:
        """Get nodes from slurmctld."""
        data = self._get(f"/slurm/{self.ver}/nodes")
        return [self.adapter.parse_node(n) for n in data.get("nodes", [])]

    def get_reservations(self) -> List[Dict]:
        """Get active reservations."""
        data = self._get(f"/slurm/{self.ver}/reservations")
        now = time.time()
        reservations = []
        for r in data.get("reservations", []):
            parsed = self.adapter.parse_reservation(r)
            # Only include active reservations
            if parsed["end_time"] > now:
                reservations.append(parsed)
        return reservations

    def get_accounts(self) -> List[Dict]:
        """Get accounts from slurmdbd."""
        data = self._get(f"/slurmdb/{self.ver}/accounts")
        return [{"name": a.get("name", ""),
                 "parent": a.get("parent_account", a.get("parent", ""))}
                for a in data.get("accounts", [])]

    def get_diag(self) -> Dict:
        """Get scheduler diagnostics."""
        data = self._get(f"/slurm/{self.ver}/diag")
        stats = data.get("statistics", data)
        gv = self.adapter.get_value
        return {
            "server_thread_count": gv(stats.get("server_thread_count"), 0),
            "agent_queue_size": gv(stats.get("agent_queue_size"), 0),
            "jobs_submitted": gv(stats.get("jobs_submitted"), 0),
            "schedule_cycle_mean": gv(stats.get("schedule_cycle_mean"), 0),
            "bf_backfilled_jobs": gv(stats.get("bf_backfilled_jobs"), 0),
        }

    def get_cluster_name(self) -> str:
        """Get cluster name from hostname (e.g., 'controller-1' -> 'controller')."""
        return platform.node().rsplit('-', 1)[0]

    def test_connection(self) -> bool:
        """Test API connectivity."""
        try:
            self._get(f"/slurm/{self.ver}/ping")
            return True
        except Exception:
            try:
                self.get_diag()
                return True
            except Exception:
                return False


# =============================================================================
# Prometheus Metrics
# =============================================================================

class PrometheusMetrics:
    """Prometheus metrics used by the Slurm dashboards."""

    def __init__(self, prefix: str = "slurm"):
        p = prefix

        # === Job info (for NVML correlation) ===
        self.job_info = Gauge(f"{p}_job_info", "Job metadata (1=running)",
            ["cluster_name", "job_id", "user", "account", "account_l1", "account_l2",
             "account_l3", "partition", "qos", "state"])

        # === Job to node mapping (bounded cardinality - only running jobs) ===
        self.job_nodes = Gauge(f"{p}_job_nodes", "Job to node mapping (1=allocated)",
            ["cluster_name", "job_id", "node"])

        # === Node metrics ===
        self.nodes_by_state = Gauge(f"{p}_nodes", "Nodes by state", ["cluster_name", "state"])
        self.nodes_total = Gauge(f"{p}_nodes_total", "Total nodes", ["cluster_name"])

        # === CPU metrics (existing dashboard-compatible names) ===
        self.cpus_total = Gauge(f"{p}_cpus_total", "Total CPUs", ["cluster_name"])
        self.effective_cpus_total = Gauge(f"{p}_effective_cpus_total",
            "Total CPUs available for scheduling", ["cluster_name"])
        self.cpus_alloc = Gauge(f"{p}_cpus_allocated", "Allocated CPUs", ["cluster_name"])

        # === GPU metrics (existing dashboard-compatible names) ===
        self.gpus_total = Gauge(f"{p}_gpus_total", "Total GPUs", ["cluster_name"])
        self.gpus_alloc = Gauge(f"{p}_gpus_allocated", "Allocated GPUs", ["cluster_name"])

        # === Job counts ===
        self.jobs_running = Gauge(f"{p}_jobs_running", "Running jobs", ["cluster_name"])
        self.jobs_pending = Gauge(f"{p}_jobs_pending", "Pending jobs", ["cluster_name"])
        self.jobs_by_state = Gauge(f"{p}_jobs_total", "Jobs by state", ["cluster_name", "state"])
        self.gpus_in_jobs = Gauge(f"{p}_gpus_in_jobs", "GPUs in running jobs", ["cluster_name"])
        self.cpus_in_jobs = Gauge(f"{p}_cpus_in_jobs", "CPUs in running jobs", ["cluster_name"])

        # === Per-partition metrics (existing dashboard-compatible names) ===
        self.partition_jobs_cpus = Gauge(f"{p}_partition_jobs_cpus_total",
            "Total CPUs consumed by jobs in partition", ["partition"])
        self.partition_jobs_nodes = Gauge(f"{p}_partition_jobs_nodes_total",
            "Total Nodes allocated for jobs in partition", ["partition"])
        self.partition_jobs_gpus = Gauge(f"{p}_partition_jobs_gpus_total",
            "Total GPUs consumed by jobs in partition", ["partition"])

        # === Per-user metrics (existing dashboard-compatible names) ===
        self.user_gpus = Gauge(f"{p}_alloc_gpus_user_count", "GPUs allocated to user", ["user"])
        self.user_cpus = Gauge(f"{p}_alloc_cpus_user_count", "CPUs allocated to user", ["user"])
        self.user_nodes = Gauge(f"{p}_alloc_nodes_user_count", "Nodes allocated to user", ["user"])

        # === Reservation metrics (existing dashboard-compatible names) ===
        self.reservation_nodes = Gauge(f"{p}_active_reservations_nodes_total",
            "Total Nodes reserved", ["reservation"])
        self.reservation_cores = Gauge(f"{p}_active_reservations_cores_total",
            "Total Cores reserved", ["reservation"])
        self.reservation_cpus = Gauge(f"{p}_active_reservations_cpus_total",
            "Total CPUs reserved", ["reservation"])

        # === Per-partition node metrics (existing dashboard-compatible names) ===
        self.partition_idle_nodes = Gauge(f"{p}_partition_idle_nodes_total",
            "Idle nodes in partition", ["partition"])
        self.partition_idle_cpus = Gauge(f"{p}_partition_idle_cpus_total",
            "Idle CPUs in partition", ["partition"])
        self.partition_idle_gpus = Gauge(f"{p}_partition_idle_gpus_total",
            "Idle GPUs in partition", ["partition"])
        self.partition_node_state = Gauge(f"{p}_partition_node_state_count",
            "Node count by state per partition", ["partition", "state"])

        # === Per-reservation node metrics (existing dashboard-compatible names) ===
        self.reservation_idle_nodes = Gauge(f"{p}_reservation_idle_nodes_total",
            "Idle nodes in reservation", ["reservation"])
        self.reservation_used_cpus = Gauge(f"{p}_reservation_used_cpus_total",
            "Used CPUs in reservation", ["reservation"])
        self.reservation_used_gpus = Gauge(f"{p}_reservation_used_gpus_total",
            "Used GPUs in reservation", ["reservation"])
        self.reservation_idle_cpus = Gauge(f"{p}_reservation_idle_cpus_total",
            "Idle CPUs in reservation", ["reservation"])
        self.reservation_idle_gpus = Gauge(f"{p}_reservation_idle_gpus_total",
            "Idle GPUs in reservation", ["reservation"])

        # === Per-account metrics ===
        self.account_jobs = Gauge(f"{p}_account_jobs", "Jobs by account",
            ["cluster_name", "account_l1", "account_l2", "state"])
        self.account_gpus = Gauge(f"{p}_account_gpus", "GPUs by account (running)",
            ["cluster_name", "account_l1", "account_l2"])
        self.account_nodes = Gauge(f"{p}_account_nodes", "Nodes by account (running)",
            ["cluster_name", "account_l1", "account_l2"])

        # === Collection metrics ===
        self.collection_time = Gauge(f"{p}_collection_seconds", "Collection time", ["cluster_name"])

        # === Per-node state from sinfo (for Grafana drill-down) ===
        self.node_state = Gauge(f"{p}_node_state",
            "One-hot Slurm node state per (node, partition)",
            ["node", "partition", "state", "vendor", "gpus", "cpus", "mem", "load_alloc", "load_total", "features"])
        self.node_state_count = Gauge(f"{p}_node_state_count",
            "Count of nodes by state (from sinfo)", ["state"])
        self.node_state_scrape_timestamp = Gauge(f"{p}_node_state_scrape_timestamp",
            "Unix timestamp of last successful sinfo-based node-state scrape")

    def update_jobs(self, jobs: List[Dict], cluster: str):
        """Update job metrics."""
        self.job_info._metrics.clear()
        self.job_nodes._metrics.clear()
        self.partition_jobs_cpus._metrics.clear()
        self.partition_jobs_nodes._metrics.clear()
        self.partition_jobs_gpus._metrics.clear()
        self.user_gpus._metrics.clear()
        self.user_cpus._metrics.clear()
        self.user_nodes._metrics.clear()
        self.account_jobs._metrics.clear()
        self.account_gpus._metrics.clear()
        self.account_nodes._metrics.clear()
        self.jobs_by_state._metrics.clear()

        running = pending = total_gpus = total_cpus = 0
        by_state = {}
        by_account = {}  # key: (l1, l2, state), value: {"jobs": N, "gpus": N, "nodes": set()}
        by_partition = {}
        by_user = {}

        for j in jobs:
            state = j["state"]
            by_state[state] = by_state.get(state, 0) + 1

            partition = j["partition"]
            user = j["user"]

            # Use "none" for empty values to ensure metrics are always emitted with valid labels
            key = (j["account_l1"] or "unknown", j["account_l2"] or "none", state)
            if key not in by_account:
                by_account[key] = {"jobs": 0, "gpus": 0, "nodes": set()}
            by_account[key]["jobs"] += 1

            if state == "RUNNING":
                running += 1
                job_gpus = j["num_gpus"]
                job_cpus = j["num_cpus"] or j["alloc_cpus"]
                job_node_list = j.get("node_list", [])

                total_gpus += job_gpus
                total_cpus += job_cpus
                by_account[key]["gpus"] += job_gpus
                by_account[key]["nodes"].update(job_node_list)

                # Per-partition: track unique nodes using a set
                if partition not in by_partition:
                    by_partition[partition] = {"cpus": 0, "nodes": set(), "gpus": 0}
                by_partition[partition]["cpus"] += job_cpus
                by_partition[partition]["nodes"].update(job_node_list)
                by_partition[partition]["gpus"] += job_gpus

                # Per-user: track unique nodes using a set
                if user not in by_user:
                    by_user[user] = {"cpus": 0, "nodes": set(), "gpus": 0}
                by_user[user]["cpus"] += job_cpus
                by_user[user]["nodes"].update(job_node_list)
                by_user[user]["gpus"] += job_gpus

                # Job info for NVML correlation
                self.job_info.labels(
                    cluster_name=cluster, job_id=str(j["job_id"]), user=user or "unknown",
                    account=j["account"] or "unknown", account_l1=j["account_l1"] or "unknown",
                    account_l2=j["account_l2"] or "none", account_l3=j["account_l3"] or "none",
                    partition=partition or "default", qos=j["qos"] or "normal", state=state
                ).set(1)

                # Job to node mapping (bounded cardinality - only running jobs)
                for node in job_node_list:
                    self.job_nodes.labels(
                        cluster_name=cluster,
                        job_id=str(j["job_id"]),
                        node=node
                    ).set(1)

            elif state == "PENDING":
                pending += 1

        self.jobs_running.labels(cluster_name=cluster).set(running)
        self.jobs_pending.labels(cluster_name=cluster).set(pending)
        self.gpus_in_jobs.labels(cluster_name=cluster).set(total_gpus)
        self.cpus_in_jobs.labels(cluster_name=cluster).set(total_cpus)

        logger.debug(f"Job stats: running={running}, pending={pending}, accounts={len(by_account)}")

        for state, count in by_state.items():
            self.jobs_by_state.labels(cluster_name=cluster, state=state).set(count)

        # Emit account metrics - always emit at least one set to ensure metric exists
        if by_account:
            for (l1, l2, state), data in by_account.items():
                self.account_jobs.labels(cluster_name=cluster, account_l1=l1, account_l2=l2, state=state).set(data["jobs"])
                if state == "RUNNING":
                    self.account_gpus.labels(cluster_name=cluster, account_l1=l1, account_l2=l2).set(data["gpus"])
                    self.account_nodes.labels(cluster_name=cluster, account_l1=l1, account_l2=l2).set(len(data["nodes"]))
        else:
            # Emit default metrics so the metric name exists in Prometheus
            self.account_jobs.labels(cluster_name=cluster, account_l1="unknown", account_l2="none", state="RUNNING").set(0)
            self.account_jobs.labels(cluster_name=cluster, account_l1="unknown", account_l2="none", state="PENDING").set(0)
            self.account_gpus.labels(cluster_name=cluster, account_l1="unknown", account_l2="none").set(0)
            self.account_nodes.labels(cluster_name=cluster, account_l1="unknown", account_l2="none").set(0)

        # Per-partition existing dashboard-compatible metrics: nodes is a set of unique node names.
        for partition, data in by_partition.items():
            self.partition_jobs_cpus.labels(partition=partition).set(data["cpus"])
            self.partition_jobs_nodes.labels(partition=partition).set(len(data["nodes"]))
            self.partition_jobs_gpus.labels(partition=partition).set(data["gpus"])

        # Per-user existing dashboard-compatible metrics: nodes is a set of unique node names.
        for user, data in by_user.items():
            self.user_cpus.labels(user=user).set(data["cpus"])
            self.user_nodes.labels(user=user).set(len(data["nodes"]))
            self.user_gpus.labels(user=user).set(data["gpus"])

    def update_nodes(self, nodes: List[Dict], cluster: str):
        """Update node metrics."""
        self.nodes_by_state._metrics.clear()
        self.partition_idle_nodes._metrics.clear()
        self.partition_idle_cpus._metrics.clear()
        self.partition_idle_gpus._metrics.clear()
        self.partition_node_state._metrics.clear()
        self.reservation_idle_nodes._metrics.clear()
        self.reservation_used_cpus._metrics.clear()
        self.reservation_used_gpus._metrics.clear()
        self.reservation_idle_cpus._metrics.clear()
        self.reservation_idle_gpus._metrics.clear()

        by_state = {}
        total_gpus = alloc_gpus = 0
        total_cpus = alloc_cpus = effective_cpus = 0

        # Per-partition metrics
        partition_idle_nodes = {}
        partition_idle_cpus = {}
        partition_idle_gpus = {}
        partition_node_states = {}

        # Per-reservation metrics
        reservation_idle_nodes = {}
        reservation_used_cpus = {}
        reservation_used_gpus = {}
        reservation_idle_cpus = {}
        reservation_idle_gpus = {}

        for n in nodes:
            state = n["state"]
            states = n.get("states", [state])
            by_state[state] = by_state.get(state, 0) + 1

            total_gpus += n["total_gpus"]
            alloc_gpus += n["alloc_gpus"]
            total_cpus += n["cpus"]
            alloc_cpus += n["alloc_cpus"]
            effective_cpus += n["effective_cpus"]

            is_idle = "IDLE" in states or state == "IDLE"
            node_idle_cpus = n.get("idle_cpus", n["cpus"] - n["alloc_cpus"])
            node_idle_gpus = n.get("idle_gpus", n["total_gpus"] - n["alloc_gpus"])

            # Per-partition metrics
            for partition in n.get("partitions", []):
                # Node state count per partition - only count primary state (not all states like DYNAMIC_NORM)
                if partition not in partition_node_states:
                    partition_node_states[partition] = {}
                partition_node_states[partition][state] = partition_node_states[partition].get(state, 0) + 1

                # Idle nodes per partition
                if is_idle:
                    partition_idle_nodes[partition] = partition_idle_nodes.get(partition, 0) + 1

                # Idle CPUs/GPUs per partition (accumulate regardless of node state)
                partition_idle_cpus[partition] = partition_idle_cpus.get(partition, 0) + node_idle_cpus
                partition_idle_gpus[partition] = partition_idle_gpus.get(partition, 0) + node_idle_gpus

            # Per-reservation metrics
            resv = n.get("reservation", "")
            if resv:
                if is_idle:
                    reservation_idle_nodes[resv] = reservation_idle_nodes.get(resv, 0) + 1
                reservation_used_cpus[resv] = reservation_used_cpus.get(resv, 0) + n["alloc_cpus"]
                reservation_used_gpus[resv] = reservation_used_gpus.get(resv, 0) + n["alloc_gpus"]
                reservation_idle_cpus[resv] = reservation_idle_cpus.get(resv, 0) + node_idle_cpus
                reservation_idle_gpus[resv] = reservation_idle_gpus.get(resv, 0) + node_idle_gpus

        self.nodes_total.labels(cluster_name=cluster).set(len(nodes))

        for state, count in by_state.items():
            self.nodes_by_state.labels(cluster_name=cluster, state=state).set(count)

        # Always emit IDLE state (even if 0) so dashboard queries work
        if "IDLE" not in by_state:
            self.nodes_by_state.labels(cluster_name=cluster, state="IDLE").set(0)

        # Legacy compatible (uses cluster_name label)
        self.cpus_total.labels(cluster_name=cluster).set(total_cpus)
        self.effective_cpus_total.labels(cluster_name=cluster).set(effective_cpus)
        self.gpus_total.labels(cluster_name=cluster).set(total_gpus)

        # New style
        self.gpus_alloc.labels(cluster_name=cluster).set(alloc_gpus)
        self.cpus_alloc.labels(cluster_name=cluster).set(alloc_cpus)

        # Per-partition node metrics with existing dashboard-compatible names.
        # Use partition_node_states keys as source of all partitions
        all_partitions = set(partition_node_states.keys())
        for partition in all_partitions:
            # Emit idle nodes (0 if none)
            self.partition_idle_nodes.labels(partition=partition).set(partition_idle_nodes.get(partition, 0))
            # Emit idle CPUs/GPUs
            self.partition_idle_cpus.labels(partition=partition).set(partition_idle_cpus.get(partition, 0))
            self.partition_idle_gpus.labels(partition=partition).set(partition_idle_gpus.get(partition, 0))
            # Emit node states (including IDLE=0 if not present)
            states_dict = partition_node_states.get(partition, {})
            for state, count in states_dict.items():
                self.partition_node_state.labels(partition=partition, state=state).set(count)
            if "IDLE" not in states_dict:
                self.partition_node_state.labels(partition=partition, state="IDLE").set(0)

        # Per-reservation node metrics with existing dashboard-compatible names.
        for resv, count in reservation_idle_nodes.items():
            self.reservation_idle_nodes.labels(reservation=resv).set(count)
        for resv, cpus in reservation_used_cpus.items():
            self.reservation_used_cpus.labels(reservation=resv).set(cpus)
        for resv, gpus in reservation_used_gpus.items():
            self.reservation_used_gpus.labels(reservation=resv).set(gpus)
        for resv, cpus in reservation_idle_cpus.items():
            self.reservation_idle_cpus.labels(reservation=resv).set(cpus)
        for resv, gpus in reservation_idle_gpus.items():
            self.reservation_idle_gpus.labels(reservation=resv).set(gpus)

    def update_reservations(self, reservations: List[Dict]):
        """Update reservation metrics."""
        self.reservation_nodes._metrics.clear()
        self.reservation_cores._metrics.clear()
        self.reservation_cpus._metrics.clear()

        for r in reservations:
            name = r["name"]
            self.reservation_nodes.labels(reservation=name).set(r["node_count"])
            self.reservation_cores.labels(reservation=name).set(r["core_count"])
            self.reservation_cpus.labels(reservation=name).set(r["cpus"])

    def update_node_state_from_sinfo(self):
        """Export per-node state labels using sinfo command.

        This provides detailed per-node state information for Grafana drill-down,
        with labels for partition, state, gpus, cpus, memory, load, and features.
        Also emits slurm_node_state_count{state} for time series panels.
        """
        # Always update timestamp to track last attempt
        self.node_state_scrape_timestamp.set(int(time.time()))

        # Common states - always emit these (even if 0) for continuous time series
        common_states = ["IDLE", "ALLOCATED", "MIXED", "DOWN", "DRAIN", "DRAINED",
                         "COMPLETING", "RESERVED", "MAINT", "FAIL", "FAILING"]
        state_counts = {s: 0 for s in common_states}
        seen_nodes = {}  # Track node -> state to avoid double counting

        cmd = ["sinfo", "-h", "-N", "-o", "%N|%P|%T|%G|%c|%m|%C|%f"]
        try:
            out = subprocess.check_output(
                cmd,
                universal_newlines=True,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"sinfo failed: {e}")
            # Clear metrics on failure so stale data doesn't persist
            self.node_state._metrics.clear()
            self.node_state_count._metrics.clear()
            # Still emit zero counts for common states
            for state in common_states:
                self.node_state_count.labels(state=state).set(0)
            return

        # Clear previous label set to avoid stale node labels
        self.node_state._metrics.clear()
        self.node_state_count._metrics.clear()

        for line in out.strip().splitlines():
            try:
                node, parts, state, gres, cpus, mem, cpu_load, features = line.split("|", 7)
            except ValueError:
                continue

            partitions = [p.rstrip("*").strip() for p in parts.split(",") if p.strip()]
            gpu_count, gpu_vendor = _parse_gpu_details(gres)
            state_full = _base_state(state)
            load_alloc, load_total = _parse_alloc_total(cpu_load)

            # Count unique nodes per state (node may appear multiple times for different partitions)
            if node not in seen_nodes:
                seen_nodes[node] = state_full
                # Get base state without suffix for counting
                base = state_full.rstrip("~*$")
                if base in state_counts:
                    state_counts[base] += 1
                else:
                    state_counts[base] = 1

            for part in partitions or ["__none__"]:
                self.node_state.labels(
                    node=node,
                    partition=part,
                    state=state_full,
                    vendor=gpu_vendor,
                    gpus=str(gpu_count),
                    cpus=str(cpus).strip(),
                    mem=str(mem).strip(),
                    load_alloc=str(load_alloc).strip(),
                    load_total=str(load_total).strip(),
                    features=str(features).strip(),
                ).set(1)

        # Emit state counts (always emit common states even if 0)
        for state, count in state_counts.items():
            self.node_state_count.labels(state=state).set(count)

        logger.debug(f"Updated node_state from sinfo: {len(seen_nodes)} nodes")


# =============================================================================
# Main Collector
# =============================================================================

class SlurmRestCollector:
    """Main collector and exporter."""

    def __init__(self, url: str, port: int = 9901, token: str = None,
                 version: str = None, cluster: str = None,
                 prefix: str = "slurm"):
        self.client = SlurmRestClient(url, token=token, version=version)
        self.port = port
        self.cluster = cluster
        self.metrics = PrometheusMetrics(prefix)
        self.account_hierarchy = {}  # Maps account name -> [root, l1, l2, ...] ancestors

    def _build_account_hierarchy(self):
        """Build account hierarchy map from slurmdb accounts."""
        try:
            accounts = self.client.get_accounts()
            # Build parent map: child -> parent
            parent_map = {a["name"]: a["parent"] for a in accounts if a["name"]}

            # For each account, build its ancestry path (from root to leaf)
            for account in parent_map:
                path = []
                current = account
                visited = set()
                while current and current not in visited:
                    visited.add(current)
                    path.insert(0, current)
                    current = parent_map.get(current, "")

                # path is now [root, l1, l2, ..., account]
                # We want l1, l2, l3 where l1 is first child of root
                if len(path) > 1:
                    # Skip 'root' if it's the first element
                    if path[0] in ('root', 'Root'):
                        path = path[1:]
                self.account_hierarchy[account] = path

            logger.info(f"Built account hierarchy: {len(self.account_hierarchy)} accounts")
            logger.debug(f"Account hierarchy: {self.account_hierarchy}")
        except Exception as e:
            logger.warning(f"Failed to build account hierarchy: {e}")

    def _resolve_account_hierarchy(self, account: str) -> tuple:
        """Resolve account to (l1, l2, l3) based on hierarchy."""
        if not account:
            return ("unknown", "none", "none")

        # Check if we have hierarchy info
        path = self.account_hierarchy.get(account, [account])

        l1 = path[0] if len(path) >= 1 else account
        l2 = path[1] if len(path) >= 2 else "none"
        l3 = path[2] if len(path) >= 3 else "none"

        return (l1 or "unknown", l2 or "none", l3 or "none")

    def start(self):
        """Initialize client and start Prometheus server."""
        self.client.detect_version()
        if not self.cluster:
            self.cluster = self.client.get_cluster_name()
        # Build account hierarchy on startup
        self._build_account_hierarchy()
        start_http_server(self.port)
        logger.info(f"Prometheus metrics on port {self.port}")

        logger.info(f"Started: cluster={self.cluster}, api={self.client.ver}")

    def collect(self) -> int:
        """Run collection cycle."""
        start = time.time()
        jobs_count = 0
        nodes_count = 0
        reservations_count = 0
        errors = 0

        # Refresh account hierarchy periodically
        if not self.account_hierarchy:
            self._build_account_hierarchy()

        try:
            jobs = self.client.get_jobs()
            jobs_count = len(jobs)

            # Resolve account hierarchy for each job
            for job in jobs:
                account = job.get("account", "")
                l1, l2, l3 = self._resolve_account_hierarchy(account)
                job["account_l1"] = l1
                job["account_l2"] = l2
                job["account_l3"] = l3

            self.metrics.update_jobs(jobs, self.cluster)
        except Exception as e:
            logger.error(f"Job collection failed: {e}")
            errors += 1

        try:
            nodes = self.client.get_nodes()
            nodes_count = len(nodes)
            self.metrics.update_nodes(nodes, self.cluster)
        except Exception as e:
            logger.error(f"Node collection failed: {e}")
            errors += 1

        try:
            reservations = self.client.get_reservations()
            reservations_count = len(reservations)
            self.metrics.update_reservations(reservations)
        except Exception as e:
            logger.error(f"Reservation collection failed: {e}")
            errors += 1

        # Always try to export per-node state labels from sinfo
        try:
            self.metrics.update_node_state_from_sinfo()
        except Exception as e:
            logger.warning(f"sinfo node state collection failed: {e}")

        duration = time.time() - start
        self.metrics.collection_time.labels(cluster_name=self.cluster).set(duration)

        logger.info(f"Collected {jobs_count} jobs, {nodes_count} nodes, "
                    f"{reservations_count} reservations in {duration:.2f}s")
        return errors

    def run(self, interval: int):
        """Run collection loop."""
        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())

        while not stop.is_set():
            try:
                self.collect()
            except Exception as e:
                logger.error(f"Collection failed: {e}")
            stop.wait(interval)


# =============================================================================
# CLI
# =============================================================================

def main():
    p = argparse.ArgumentParser(description="Slurm REST API Prometheus Exporter",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--url", "-u", default=os.environ.get("SLURMRESTD_URL", "http://localhost:6820"))
    p.add_argument("--token", default=os.environ.get("SLURM_JWT"))
    p.add_argument("--version", help="API version (auto-detect if not set)")
    p.add_argument("--port", "-p", type=int, default=9901, help="Prometheus port")
    p.add_argument("--interval", "-i", type=int, default=60, help="Collection interval (seconds)")
    p.add_argument("--cluster", "-c", help="Cluster name")
    p.add_argument("--prefix", default="slurm", help="Metrics prefix")
    p.add_argument("--once", action="store_true", help="Collect once and exit")
    p.add_argument("--test", action="store_true", help="Test connection and exit")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    args = p.parse_args()

    logging.getLogger().setLevel(getattr(logging, args.log_level))

    if args.test:
        print(f"Testing {args.url}...")
        client = SlurmRestClient(args.url, token=args.token, version=args.version)
        client.detect_version()
        if client.test_connection():
            print(f"OK: version={client.ver}, cluster={client.get_cluster_name()}")
            nodes = client.get_nodes()
            jobs = client.get_jobs()
            print(f"Nodes: {len(nodes)}, Jobs: {len(jobs)}")
            print(f"Reservations: {len(client.get_reservations())}")

            # Show account hierarchy
            accounts = client.get_accounts()
            print(f"\nAccounts ({len(accounts)}):")
            for a in accounts[:10]:
                print(f"  {a['name']} -> parent: {a['parent']}")

            # Show job accounts
            if jobs:
                print("\nJob accounts (first 5):")
                for j in jobs[:5]:
                    print(f"  Job {j['job_id']}: account={j['account']}, state={j['state']}")
            return 0
        print("FAILED")
        return 1

    collector = SlurmRestCollector(
        url=args.url, port=args.port, token=args.token, version=args.version,
        cluster=args.cluster, prefix=args.prefix)

    collector.start()

    if args.once:
        errors = collector.collect()
        return 0 if errors == 0 else 1

    collector.run(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
