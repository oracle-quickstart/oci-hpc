#!/usr/bin/env python3
###########################
# ncclscout.py – NCCL/RCCL connectivity & bandwidth diagnostic for OCI Slurm GPU clusters.
# Author: Nuruddin Ahmed
# Date: 2025-12-19
# Updated: 2026-04-29 — Added AMD MI300X, MI355X-v0, MI355X-v1 support via sbatch
###########################
# How to use this script?
# 1. python3 ncclscout.py hostfile_name --> Recommended: runs test sequentially on hosts in file
# 2. python3 ncclscout.py host1 host2   --> Test only between two specific nodes
# 3. python3 ncclscout.py               --> Without any argument, uses all nodes from sinfo
# 4. python3 ncclscout.py --parallel    --> Run in parallel (not recommended on production)
##########################
# This tool runs NCCL/RCCL all-reduce bandwidth tests between node pairs to quickly identify
# unreachable nodes, timeouts, and low-bandwidth "bad" nodes. It automatically detects
# GPU shape/model to apply the correct expected bandwidth threshold, logs full output
# to nccl_test.log, and writes a readable run summary to nccl_test_screen.log.
#
# Use it before production workloads (or when debugging) to validate multi-node GPU
# communication health across the cluster.
##########################

import subprocess
import os
import shutil
import time
import concurrent.futures
import uuid
from threading import Lock
import argparse
import itertools
from collections import Counter
from datetime import datetime

# ---------------------------------------------------------------------------
# GPU shape definitions
# CHANGE 1: Added AMD shapes (MI300X, MI355X)
#           NVIDIA shapes unchanged from original
# ---------------------------------------------------------------------------
GPU_SHAPES = {
    # ── NVIDIA (unchanged) ──────────────────────────────────────────────────
    "A100": {"shapes": ["BM.GPU4.8", "BM.GPU.B4.8", "BM.GPU.A100-v2.8"], "threshold": 185.0, "vendor": "nvidia", "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "H100": {"shapes": ["BM.GPU.H100.8"],  "threshold": 440.0, "vendor": "nvidia", "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "H200": {"shapes": ["BM.GPU.H200.8"],  "threshold": 440.0, "vendor": "nvidia", "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "B200": {"shapes": ["BM.GPU.B200.8"],  "threshold": 440.0, "vendor": "nvidia", "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "B300": {"shapes": ["BM.GPU.B300.8"],  "threshold": 750.0, "vendor": "nvidia", "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    # ── AMD (new) ───────────────────────────────────────────────────────────
    "MI300X": {"shapes": ["BM.GPU.MI300X.8"],  "threshold": 350.0, "vendor": "amd", "sbatch": "/opt/oci-hpc/samples/gpu/rccl_run_allreduce.sbatch"},
    "MI355X": {"shapes": ["BM.GPU.MI355X.8"],  "threshold": 400.0, "vendor": "amd", "sbatch": "/opt/oci-hpc/samples/gpu/rccl_run_allreduce.sbatch"},
}

SBATCH_POLL_INTERVAL = 10   # seconds between squeue polls
SBATCH_TIMEOUT       = 600  # seconds before giving up on a submitted job

# ANSI escape codes for colors
COLOR_GREEN  = '\033[92m'
COLOR_RED    = '\033[91m'
COLOR_YELLOW = '\033[93m'
COLOR_RESET  = '\033[0m'

# Log files
NCCL_LOG_FILE   = 'nccl_test.log'
SCREEN_LOG_FILE = 'nccl_test_screen.log'

# Global lock for thread-safe logging
log_lock      = Lock()
progress_lock = Lock()

def log_and_print(message, color=""):
    """Print message to screen and log to file"""
    with log_lock:
        if color:
            print(f"{color}{message}{COLOR_RESET}")
        else:
            print(message)
        with open(SCREEN_LOG_FILE, 'a') as f:
            f.write(f"{message}\n")

def log_and_print_no_newline(message, color=""):
    """Print message without newline and log to file"""
    with log_lock:
        if color:
            print(f"{color}{message}{COLOR_RESET}", end='')
        else:
            print(message, end='')
        with open(SCREEN_LOG_FILE, 'a') as f:
            f.write(message)

def init_log_files():
    """Initialize log files with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SCREEN_LOG_FILE, 'a') as f:
        f.write(f"\n{'='*70}\n")
        f.write(f"NCCL/RCCL Test Started: {timestamp}\n")
        f.write(f"{'='*70}\n")
    with open(NCCL_LOG_FILE, 'a') as f:
        f.write(f"\n{'='*70}\n")
        f.write(f"NCCL/RCCL Test Started: {timestamp}\n")
        f.write(f"{'='*70}\n")

def ensure_scripts_executable():
    seen = set()
    for config in GPU_SHAPES.values():
        for key in ("script", "sbatch"):
            path = config.get(key)
            if path and path not in seen:
                seen.add(path)

                if not os.path.exists(path):
                    continue
                try:
                    subprocess.run(['chmod', '+x', path], check=True)
                except subprocess.CalledProcessError as e:
                    log_and_print(f"Error setting executable permission for {path}: {e}")

def copy_node_ordering_script():
    source_path      = "/opt/oci-hpc/bin/node_ordering_by_rack.py"
    destination_path = "/home/ubuntu/node_ordering_by_rack.py"
    try:
        shutil.copy(source_path, destination_path)
    except FileNotFoundError:
        log_and_print(f"Error: {source_path} not found.")
    except PermissionError:
        log_and_print(f"Error: Permission denied when copying {source_path}.")
    except Exception as e:
        log_and_print(f"Error copying file: {e}")

def get_hosts_from_sinfo():
    try:
        hosts_output = subprocess.check_output(['sinfo', '-N', '-h', '-o', '%N'])
        hosts = [line.strip() for line in hosts_output.decode('utf-8').split('\n') if line.strip()]
        host_counts = Counter(hosts)
        duplicates  = {host: count for host, count in host_counts.items() if count > 1}
        unique_hosts = list(dict.fromkeys(hosts))
        if duplicates:
            log_and_print(f"Total Nodes: {len(unique_hosts)}")
        return unique_hosts
    except subprocess.CalledProcessError as e:
        log_and_print(f"Error fetching hosts from sinfo: {e}")
        return []

def get_hosts_from_file(filename):
    try:
        with open(filename, 'r') as file:
            hosts = [line.strip() for line in file if line.strip()]
            unique_hosts = list(dict.fromkeys(hosts))
            if len(unique_hosts) < len(hosts):
                log_and_print("Duplicate hosts found and removed, host file updated...")
                with open(filename, 'w') as file:
                    for host in unique_hosts:
                        file.write(f"{host}\n")
            return unique_hosts
    except FileNotFoundError:
        log_and_print(f"Error: Host file '{filename}' not found.")
        return []

def check_host_reachability(host):
    try:
        subprocess.check_call(['ssh', '-o', 'ConnectTimeout=5', host, 'exit'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def check_hosts_concurrently(hosts, max_workers=10):
    reachable_hosts   = []
    unreachable_hosts = []

    def check_and_return(host):
        if check_host_reachability(host):
            return (host, True)
        return (host, False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_and_return, host): host for host in hosts}
        for future in concurrent.futures.as_completed(futures):
            host = futures[future]
            try:
                result_host, is_reachable = future.result()
                if is_reachable:
                    reachable_hosts.append(result_host)
                else:
                    unreachable_hosts.append(result_host)
                    log_and_print(f"Host {result_host} is unreachable.", COLOR_RED)
            except Exception as e:
                log_and_print(f"Error checking host {host}: {e}")
                unreachable_hosts.append(host)
    return reachable_hosts, unreachable_hosts

def get_remote_node_shape(node):
    try:
        cmd = (
            f'ssh {node} '
            f'"curl -sH \\"Authorization: Bearer Oracle\\" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape"'
        )
        return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        log_and_print(f"Error fetching node shape from {node}: {e}")
        return None

# ---------------------------------------------------------------------------
# CHANGE 2: determine_gpu_model returns (model, config) instead of
#           (model, threshold, script) so vendor can be checked downstream
# ---------------------------------------------------------------------------
def determine_gpu_model(shape):
    for model, config in GPU_SHAPES.items():
        if shape in config["shapes"]:
            return model, config
    log_and_print(f"Error: Unrecognized shape '{shape}'.")
    return None, None

def write_hosts_file(host1, host2):
    filename = f"hosts_{uuid.uuid4().hex}.txt"
    with open(filename, 'w') as f:
        f.write(f"{host1}\n{host2}\n")
    return filename

# ---------------------------------------------------------------------------
# CHANGE 4: New function — AMD RCCL test via sbatch
# ---------------------------------------------------------------------------
def _run_amd_rccl_test(host1, host2, config):
    """
    Submit rccl_run_allreduce.sbatch pinned to host1 and host2,
    wait for completion, parse in-place busbw from output, return it.
    """
    sbatch_script = config["sbatch"]
    out_dir       = os.path.expanduser("~")
    job_id        = None

    try:
        result = subprocess.run(
            [
                "sbatch",
                f"--nodelist={host1},{host2}",
                "--nodes=2",
                "--output", f"{out_dir}/ncclscout_%j.out",
                sbatch_script,
            ],
            capture_output=True, text=True, timeout=30,
        )

        if result.returncode != 0:
            log_and_print(
                f"sbatch submission failed for {host1},{host2}: {result.stderr.strip()}",
                COLOR_RED)
            return None

        # Parse job ID from "Submitted batch job 42"
        for token in result.stdout.strip().split():
            if token.isdigit():
                job_id = token
                break

        if not job_id:
            log_and_print(f"Could not parse job ID from sbatch output: {result.stdout}", COLOR_RED)
            return None

        out_file = f"{out_dir}/ncclscout_{job_id}.out"

        # Poll squeue until job completes
        elapsed = 0
        while elapsed < SBATCH_TIMEOUT:
            time.sleep(SBATCH_POLL_INTERVAL)
            elapsed += SBATCH_POLL_INTERVAL
            sq = subprocess.run(
                ["squeue", "--job", job_id, "-h", "-o", "%T"],
                capture_output=True, text=True,
            )
            state = sq.stdout.strip()
            if state in ("", "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL"):
                break
        else:
            subprocess.run(["scancel", job_id], capture_output=True)
            log_and_print(
                f"Job {job_id} timed out after {SBATCH_TIMEOUT}s for {host1} <-> {host2}.",
                COLOR_RED)
            return None

        if not os.path.exists(out_file):
            log_and_print(f"Output file {out_file} not found for job {job_id}.", COLOR_RED)
            return None

        with open(out_file, 'r') as f:
            output = f.read()

        with open(NCCL_LOG_FILE, 'a') as lf:
            lf.write(f"\nRCCL sbatch output for {host1} <-> {host2} (job {job_id}):\n{output}\n")

        os.remove(out_file)

        # Parse in-place busbw — same logic as original (columns[-2])
        valid_line = None
        for line in output.split('\n'):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "UTC" in line or line.lower().startswith("fri") or "mpi" in line.lower():
                continue
            columns = line.split()
            if len(columns) >= 2 and columns[-2].replace('.', '', 1).isdigit():
                valid_line = line
                break

        if not valid_line:
            log_and_print(
                f"Warning: No valid bandwidth data for {host1} and {host2}. "
                f"Check {NCCL_LOG_FILE} for details.")
            return None

        return float(valid_line.split()[-2])

    except subprocess.TimeoutExpired:
        log_and_print(f"sbatch command timed out for {host1} <-> {host2}.", COLOR_RED)
        if job_id:
            subprocess.run(["scancel", job_id], capture_output=True)
        return None
    except Exception as e:
        log_and_print(f"Unexpected error for {host1} <-> {host2}: {e}", COLOR_RED)
        if job_id:
            subprocess.run(["scancel", job_id], capture_output=True)
        return None

# ---------------------------------------------------------------------------
# CHANGE 3: run_nccl_test branches on vendor — AMD uses sbatch, NVIDIA
#           uses shell script exactly as original
# ---------------------------------------------------------------------------
def run_nccl_test(host1, host2, config, timeout=120):
    if host1 == host2:
        log_and_print(f"Error: Cannot test node {host1} with itself")
        return None

    # AMD — submit via sbatch
    if config.get("vendor") == "amd":
        return _run_amd_rccl_test(host1, host2, config)

    # NVIDIA — original shell script logic unchanged
    nccl_script = config["script"]
    hosts_file  = write_hosts_file(host1, host2)
    cmd = ['timeout', str(timeout), nccl_script, '1', hosts_file]

    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)

        with open(NCCL_LOG_FILE, 'a') as log_file:
            log_file.write(f"\nNCCL output for {host1} and {host2}:\n{output.decode('utf-8')}\n")

        valid_line = None
        for line in output.decode('utf-8').split('\n'):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "UTC" in line or line.lower().startswith("fri") or "mpi" in line.lower():
                continue
            columns = line.split()
            if len(columns) >= 2 and columns[-2].replace('.', '', 1).isdigit():
                valid_line = line
                break

        if not valid_line:
            log_and_print(f"Warning: No valid bandwidth data for {host1} and {host2}. Full output logged.")
            return None

        return float(valid_line.split()[-2])

    except subprocess.TimeoutExpired:
        log_and_print(f"Error: NCCL test timed out for pair {host1} and {host2}.")
        with open(NCCL_LOG_FILE, 'a') as log_file:
            log_file.write(f"\nNCCL TIMEOUT for {host1} and {host2}\n")
    except subprocess.CalledProcessError as e:
        log_and_print(f"Error running NCCL test between {host1} and {host2}: {e}")
        with open(NCCL_LOG_FILE, 'a') as log_file:
            log_file.write(f"\nNCCL ERROR for {host1} and {host2}: {e}\n")
    except ValueError as e:
        log_and_print(f"Error parsing bandwidth output for {host1} and {host2}: {e}")
    finally:
        if os.path.exists(hosts_file):
            os.remove(hosts_file)
    return None

# ---------------------------------------------------------------------------
# Everything below is IDENTICAL to the original script
# ---------------------------------------------------------------------------

def create_node_pairs(nodes):
    """Create pairs of nodes for testing, ensuring no self-pairing"""
    pairs   = []
    unpaired = []
    used    = set()
    i = 0
    while i < len(nodes):
        if i + 1 < len(nodes):
            if nodes[i] != nodes[i+1]:
                pairs.append((nodes[i], nodes[i+1]))
                used.add(nodes[i])
                used.add(nodes[i+1])
                i += 2
            else:
                if nodes[i] not in used:
                    unpaired.append(nodes[i])
                i += 1
        else:
            if nodes[i] not in used:
                unpaired.append(nodes[i])
            i += 1
    for node in nodes:
        if node not in used and node not in unpaired:
            unpaired.append(node)
    return pairs, unpaired

def print_progress_bar(iteration, total, prefix='', length=50):
    if total == 0:
        return
    percent       = f"{(iteration / total) * 100:.1f}"
    filled_length = int(length * iteration // total)
    bar           = '█' * filled_length + '-' * (length - filled_length)
    message       = f'\r{prefix} |{bar}| {percent}% Complete'
    print(message, end='\r')
    if iteration == total:
        print()
        with open(SCREEN_LOG_FILE, 'a') as f:
            f.write(f"{prefix} completed - {iteration}/{total} (100%)\n")

def retest_bad_nodes_with_progress(bad_nodes, good_nodes, default_config, threshold, reason="low bandwidth"):
    if not bad_nodes:
        return {}
    if not good_nodes:
        log_and_print(f"\nNo good nodes available for retesting bad nodes due to {reason}.", COLOR_RED)
        log_and_print("Attempting to find the best among bad nodes...")
        good_nodes = bad_nodes

    log_and_print(f"\n\nRetesting {len(bad_nodes)} nodes due to {reason}...")
    retest_results  = {}
    total_retests   = len(bad_nodes)
    good_nodes_list = list(good_nodes)

    if len(good_nodes_list) < len(bad_nodes):
        log_and_print(f"Note: {len(good_nodes_list)} good node(s) available to test {len(bad_nodes)} bad nodes.", COLOR_YELLOW)

    good_nodes_cycle = itertools.cycle(good_nodes_list)

    for idx, node in enumerate(bad_nodes, 1):
        test_partner = None
        attempts     = 0
        max_attempts = len(good_nodes_list)
        while attempts < max_attempts:
            candidate = next(good_nodes_cycle)
            if candidate != node:
                test_partner = candidate
                break
            attempts += 1

        if not test_partner or test_partner == node:
            log_and_print(f"\nCannot retest {node} - no different node available", COLOR_RED)
            retest_results[(node, node)] = 0.0
            continue

        # Get config for this node's shape
        shape = get_remote_node_shape(node)
        _, config = determine_gpu_model(shape)
        config = config or default_config

        log_and_print_no_newline(f"Retesting {node} with {test_partner}...")
        bandwidth = run_nccl_test(test_partner, node, config)

        if bandwidth is None:
            log_and_print(" FAILED", COLOR_RED)
            retest_results[(test_partner, node)] = 0.0
        else:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_YELLOW
            log_and_print(f" {bandwidth:.2f} GB/s", color)
            retest_results[(test_partner, node)] = bandwidth

        print_progress_bar(idx, total_retests, prefix=f'Retesting ({reason})')

    return retest_results

def categorize_nodes_with_timeout_tracking(results, global_threshold):
    """Categorize nodes based on their test results, tracking timeout failures separately"""
    final_good_nodes    = set()
    final_bad_nodes     = set()
    final_timeout_nodes = set()
    node_test_results   = {}
    all_tested          = set()

    for (host1, host2), bw in results.items():
        all_tested.add(host1)
        all_tested.add(host2)
        if host1 not in node_test_results:
            node_test_results[host1] = []
        if host2 not in node_test_results:
            node_test_results[host2] = []
        node_test_results[host1].append(bw)
        node_test_results[host2].append(bw)

    for node, bandwidths in node_test_results.items():
        valid_bws = [bw for bw in bandwidths if bw > 0]
        if valid_bws:
            best_bw = max(valid_bws)
            if best_bw >= global_threshold:
                final_good_nodes.add(node)
            else:
                final_bad_nodes.add(node)
        else:
            final_bad_nodes.add(node)
            final_timeout_nodes.add(node)

    return final_good_nodes, final_bad_nodes, final_timeout_nodes, all_tested

def print_comprehensive_summary(all_input_nodes, reachable_hosts, final_good_nodes, final_bad_nodes,
                                final_timeout_nodes, unreachable_nodes, global_threshold, results):
    """Print a comprehensive summary of all node states"""
    log_and_print("\n" + "="*70)
    log_and_print("COMPREHENSIVE NODE ACCOUNTING SUMMARY")
    log_and_print("="*70)
    log_and_print(f"\nTotal nodes provided: {len(all_input_nodes)}")
    log_and_print(f"├── Reachable nodes: {len(set(reachable_hosts))}")
    log_and_print(f"│   └── Successfully categorized: {len(final_good_nodes) + len(final_bad_nodes)}")

    if final_good_nodes:
        log_and_print(f"│       ├── Good nodes (≥ {global_threshold} GB/s): {len(final_good_nodes)}", COLOR_GREEN)
    else:
        log_and_print(f"│       ├── Good nodes (≥ {global_threshold} GB/s): 0")

    if final_bad_nodes:
        log_and_print(f"│       └── Bad nodes (< {global_threshold} GB/s or failed): {len(final_bad_nodes)}", COLOR_RED)
        if final_timeout_nodes:
            log_and_print(f"│           └── Failed all tests (timeout/error): {len(final_timeout_nodes)}", COLOR_RED)
    else:
        log_and_print(f"│       └── Bad nodes (< {global_threshold} GB/s or failed): 0")

    if unreachable_nodes:
        log_and_print(f"└── Unreachable nodes: {len(unreachable_nodes)}", COLOR_RED)
    else:
        log_and_print("└── Unreachable nodes: 0")

    total_accounted = len(final_good_nodes) + len(final_bad_nodes) + len(unreachable_nodes)
    log_and_print(f"\nVerification: {total_accounted} nodes accounted for out of {len(all_input_nodes)} total")

    if total_accounted != len(all_input_nodes):
        log_and_print("WARNING: Node count mismatch!", COLOR_RED)
        unaccounted = all_input_nodes - final_good_nodes - final_bad_nodes - unreachable_nodes
        if unaccounted:
            log_and_print(f"Unaccounted nodes: {', '.join(sorted(unaccounted))}")

    if final_good_nodes:
        log_and_print(f"\nGood Nodes ({len(final_good_nodes)}):", COLOR_GREEN)
        log_and_print("   " + ", ".join(sorted(final_good_nodes)))

    if final_bad_nodes:
        log_and_print(f"\nBad Nodes ({len(final_bad_nodes)}):", COLOR_RED)
        log_and_print("   " + ", ".join(sorted(final_bad_nodes)))
        if final_timeout_nodes:
            log_and_print(f"\n   └── Nodes that failed ALL tests ({len(final_timeout_nodes)}):", COLOR_RED)
            log_and_print("       " + ", ".join(sorted(final_timeout_nodes)))

    if unreachable_nodes:
        log_and_print(f"\nUnreachable Nodes ({len(unreachable_nodes)}):", COLOR_RED)
        log_and_print("   " + ", ".join(sorted(unreachable_nodes)))

    valid_bandwidths = [bw for bw in results.values() if bw > 0]
    if valid_bandwidths:
        log_and_print("\nBandwidth Statistics:")
        log_and_print(f"  Maximum: {max(valid_bandwidths):.2f} GB/s")
        log_and_print(f"  Minimum: {min(valid_bandwidths):.2f} GB/s")
        log_and_print(f"  Average: {sum(valid_bandwidths)/len(valid_bandwidths):.2f} GB/s")
        failed_tests = sum(1 for bw in results.values() if bw == 0.0)
        if failed_tests:
            log_and_print(f"  Failed tests: {failed_tests}")

    if final_bad_nodes or unreachable_nodes:
        log_and_print("\nPlease perform health checks on problematic nodes.", COLOR_YELLOW)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_and_print(f"\nTest completed at: {timestamp}")


def find_bad_nodes_serial(hosts):
    init_log_files()
    ensure_scripts_executable()
    copy_node_ordering_script()

    all_input_nodes   = set()
    unreachable_nodes = set()
    tested_nodes      = set()
    failed_test_nodes = set()
    timeout_nodes     = set()

    if len(hosts) == 0:
        hosts = get_hosts_from_sinfo()
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL/RCCL test on {len(hosts)} nodes from sinfo...")
    elif len(hosts) == 1:
        hosts = get_hosts_from_file(hosts[0])
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL/RCCL test on {len(hosts)} nodes from file...")
    elif len(hosts) == 2:
        host1, host2 = hosts[0], hosts[1]
        if host1 == host2:
            log_and_print(f"Error: Cannot test a node with itself ({host1})", COLOR_RED)
            return
        log_and_print(f"Running test between: {host1} and {host2}...")
        shape = get_remote_node_shape(host1)
        if not shape:
            log_and_print(f"Unable to fetch node shape from {host1}. Exiting.")
            return
        gpu_model, config = determine_gpu_model(shape)
        if not gpu_model:
            return
        bandwidth = run_nccl_test(host1, host2, config, timeout=60)
        if bandwidth is not None:
            color = COLOR_GREEN if bandwidth >= config["threshold"] else COLOR_RED
            log_and_print(f"\nResult: {host1} <-> {host2}: {bandwidth:.2f} GB/s", color)
        else:
            log_and_print(f"\nTest failed between {host1} and {host2}", COLOR_RED)
        return
    else:
        log_and_print("Usage: script.py [host_file | host1 host2]")
        return

    if not hosts:
        log_and_print("No hosts found.")
        return

    log_and_print(f"\nChecking reachability of {len(hosts)} nodes...")
    reachable_hosts, unreachable_list = check_hosts_concurrently(hosts)
    unreachable_nodes = set(unreachable_list)
    if unreachable_nodes:
        log_and_print(f"\nWarning: {len(unreachable_nodes)} nodes are unreachable and will be excluded from testing.", COLOR_RED)

    if len(reachable_hosts) < 2:
        log_and_print("Not enough reachable hosts to proceed with testing.")
        if all_input_nodes:
            print_comprehensive_summary(all_input_nodes, reachable_hosts, set(), set(),
                                        set(), unreachable_nodes, 0, {})
        return

    log_and_print("\nCreating test pairs...")
    test_pairs, unpaired = create_node_pairs(reachable_hosts)
    log_and_print(f"Created {len(test_pairs)} test pairs")
    if unpaired:
        log_and_print(f"Unpaired nodes ({len(unpaired)}): {', '.join(unpaired)}")

    results          = {}
    global_threshold = None
    default_config   = GPU_SHAPES["A100"]

    log_and_print("\nRunning NCCL/RCCL Tests sequentially...")
    for i, (host1, host2) in enumerate(test_pairs, 1):
        shape1 = get_remote_node_shape(host1)
        shape2 = get_remote_node_shape(host2)
        model1, config1 = determine_gpu_model(shape1)
        model2, config2 = determine_gpu_model(shape2)

        if not model1 or not model2:
            log_and_print(f"Skipping pair {host1}-{host2} - unrecognized shape")
            continue

        threshold = min(config1["threshold"], config2["threshold"])
        if global_threshold is None:
            global_threshold = threshold
        default_config = config1

        log_and_print_no_newline(f"Testing {host1} <-> {host2}...")
        bandwidth = run_nccl_test(host1, host2, config1)

        if bandwidth is None:
            log_and_print(" FAILED", COLOR_RED)
            failed_test_nodes.update([host1, host2])
            timeout_nodes.update([host1, host2])
            results[(host1, host2)] = 0.0
        else:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_YELLOW
            log_and_print(f" {bandwidth:.2f} GB/s", color)
            results[(host1, host2)] = bandwidth
            tested_nodes.update([host1, host2])

        print_progress_bar(i, len(test_pairs), prefix='Testing pairs')

    if unpaired:
        log_and_print(f"\n\nTesting {len(unpaired)} unpaired nodes...")
        for node in unpaired:
            test_partner = None
            for tested in tested_nodes:
                if tested != node and tested not in failed_test_nodes:
                    test_partner = tested
                    break
            if not test_partner:
                for tested in tested_nodes:
                    if tested != node:
                        test_partner = tested
                        break
            if not test_partner:
                for candidate in reachable_hosts:
                    if candidate != node:
                        test_partner = candidate
                        break

            if test_partner:
                shape = get_remote_node_shape(node)
                model, config = determine_gpu_model(shape)
                if model:
                    log_and_print_no_newline(f"Testing unpaired node {node} with {test_partner}...")
                    bandwidth = run_nccl_test(test_partner, node, config)
                    if bandwidth is None:
                        log_and_print(" FAILED", COLOR_RED)
                        failed_test_nodes.add(node)
                        timeout_nodes.add(node)
                        results[(test_partner, node)] = 0.0
                    else:
                        color = COLOR_GREEN if bandwidth >= (global_threshold or config["threshold"]) else COLOR_YELLOW
                        log_and_print(f" {bandwidth:.2f} GB/s", color)
                        results[(test_partner, node)] = bandwidth
                        tested_nodes.add(node)
            else:
                log_and_print(f"Warning: Could not find any partner to test {node}", COLOR_RED)
                failed_test_nodes.add(node)
                results[(node, node)] = 0.0

    if global_threshold is None:
        global_threshold = 185.0

    log_and_print("\n\nInitial Test Results:")
    for (host1, host2), bandwidth in sorted(results.items(), key=lambda x: x[1], reverse=True):
        if bandwidth > 0:
            color = COLOR_GREEN if bandwidth >= global_threshold else COLOR_RED
            log_and_print(f"  {host1} <-> {host2}: {bandwidth:.2f} GB/s", color)
        else:
            log_and_print(f"  {host1} <-> {host2}: FAILED", COLOR_RED)

    good_nodes = set()
    bad_nodes  = set()
    for (host1, host2), bw in results.items():
        if bw >= global_threshold:
            good_nodes.update([host1, host2])
        elif bw > 0:
            bad_nodes.update([host1, host2])
    bad_nodes = bad_nodes - good_nodes

    all_failed_nodes = (timeout_nodes | bad_nodes | failed_test_nodes) - good_nodes

    if all_failed_nodes:
        log_and_print("\n=== COMPREHENSIVE RETESTING PHASE ===", COLOR_YELLOW)
        log_and_print(f"Retesting all {len(all_failed_nodes)} problematic nodes...")

        if good_nodes:
            log_and_print("\nPhase 1: Retesting with confirmed good nodes...")
            retest_results = retest_bad_nodes_with_progress(
                all_failed_nodes, good_nodes, default_config, global_threshold,
                reason="comprehensive check")
            results.update(retest_results)
            for (host1, host2), bw in retest_results.items():
                if bw >= global_threshold:
                    good_nodes.update([host1, host2])
                    all_failed_nodes.discard(host1)
                    all_failed_nodes.discard(host2)

        remaining_bad = all_failed_nodes - good_nodes
        if remaining_bad and len(remaining_bad) > 1:
            log_and_print("\nPhase 2: Cross-testing remaining problematic nodes...")
            bad_list  = list(remaining_bad)
            bad_pairs = [(bad_list[i], bad_list[j])
                         for i in range(len(bad_list))
                         for j in range(i+1, len(bad_list))]
            for idx, (node1, node2) in enumerate(bad_pairs[:min(10, len(bad_pairs))], 1):
                log_and_print_no_newline(f"Cross-test {node1} <-> {node2}...")
                shape = get_remote_node_shape(node1)
                _, config = determine_gpu_model(shape)
                bandwidth = run_nccl_test(node1, node2, config or default_config)
                if bandwidth is None:
                    log_and_print(" FAILED", COLOR_RED)
                    results[(node1, node2)] = 0.0
                else:
                    color = COLOR_GREEN if bandwidth >= global_threshold else COLOR_YELLOW
                    log_and_print(f" {bandwidth:.2f} GB/s", color)
                    results[(node1, node2)] = bandwidth
                    if bandwidth >= global_threshold:
                        good_nodes.update([node1, node2])

    final_good_nodes, final_bad_nodes, final_timeout_nodes, all_tested = \
        categorize_nodes_with_timeout_tracking(results, global_threshold)
    print_comprehensive_summary(all_input_nodes, reachable_hosts, final_good_nodes, final_bad_nodes,
                                final_timeout_nodes, unreachable_nodes, global_threshold, results)


def find_bad_nodes_parallel(hosts):
    init_log_files()
    ensure_scripts_executable()
    copy_node_ordering_script()

    all_input_nodes   = set()
    unreachable_nodes = set()
    tested_nodes      = set()
    failed_test_nodes = set()
    timeout_nodes     = set()

    if len(hosts) == 0:
        hosts = get_hosts_from_sinfo()
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL/RCCL test on {len(hosts)} unique nodes from sinfo...")
    elif len(hosts) == 1:
        hosts = get_hosts_from_file(hosts[0])
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL/RCCL test on {len(hosts)} nodes from file...")
    elif len(hosts) == 2:
        host1, host2 = hosts[0], hosts[1]
        if host1 == host2:
            log_and_print(f"Error: Cannot test a node with itself ({host1})", COLOR_RED)
            return
        log_and_print(f"Running test between: {host1} and {host2}...")
        shape = get_remote_node_shape(host1)
        if not shape:
            log_and_print(f"Unable to fetch node shape from {host1}. Exiting.")
            return
        gpu_model, config = determine_gpu_model(shape)
        if not gpu_model:
            return
        bandwidth = run_nccl_test(host1, host2, config, timeout=120)
        if bandwidth is not None:
            color = COLOR_GREEN if bandwidth >= config["threshold"] else COLOR_RED
            log_and_print(f"\nResult: {host1} <-> {host2}: {bandwidth:.2f} GB/s", color)
        else:
            log_and_print(f"\nTest failed between {host1} and {host2}", COLOR_RED)
        return
    else:
        log_and_print("Usage: script.py [host_file | host1 host2]")
        return

    if not hosts:
        log_and_print("No hosts found.")
        return

    log_and_print(f"\nChecking reachability of {len(hosts)} nodes...")
    reachable_hosts, unreachable_list = check_hosts_concurrently(hosts)
    unreachable_nodes = set(unreachable_list)
    if unreachable_nodes:
        log_and_print(f"\nWarning: {len(unreachable_nodes)} nodes are unreachable and will be excluded from testing.", COLOR_RED)

    if len(reachable_hosts) < 2:
        log_and_print("Not enough reachable hosts to proceed.")
        return

    test_pairs, unpaired = create_node_pairs(reachable_hosts)
    log_and_print(f"Created {len(test_pairs)} test pairs for parallel testing")
    if unpaired:
        log_and_print(f"Unpaired nodes to test separately: {', '.join(unpaired)}")

    pairs_to_test    = []
    thresholds       = {}
    global_threshold = None
    default_config   = GPU_SHAPES["A100"]

    for host1, host2 in test_pairs:
        shape1 = get_remote_node_shape(host1)
        shape2 = get_remote_node_shape(host2)
        model1, config1 = determine_gpu_model(shape1)
        model2, config2 = determine_gpu_model(shape2)
        if not model1 or not model2:
            continue
        threshold = min(config1["threshold"], config2["threshold"])
        if global_threshold is None:
            global_threshold = threshold
            default_config   = config1
        thresholds[(host1, host2)] = threshold
        pairs_to_test.append((host1, host2, config1))

    if global_threshold is None:
        global_threshold = 185.0

    log_and_print("\nRunning NCCL/RCCL Tests in parallel...")
    results = {}

    with concurrent.futures.ProcessPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(run_nccl_test, h1, h2, c): (h1, h2)
                   for h1, h2, c in pairs_to_test}
        for future in concurrent.futures.as_completed(futures):
            host1, host2 = futures[future]
            try:
                bandwidth = future.result()
                if bandwidth is None:
                    failed_test_nodes.update([host1, host2])
                    timeout_nodes.update([host1, host2])
                    results[(host1, host2)] = 0.0
                    log_and_print(f"{host1} <-> {host2}: FAILED", COLOR_RED)
                else:
                    results[(host1, host2)] = bandwidth
                    tested_nodes.update([host1, host2])
                    threshold = thresholds.get((host1, host2), global_threshold)
                    color     = COLOR_GREEN if bandwidth >= threshold else COLOR_YELLOW
                    log_and_print(f"{host1} <-> {host2}: {bandwidth:.2f} GB/s", color)
            except Exception as e:
                log_and_print(f"Error in parallel test for {host1} <-> {host2}: {e}")
                failed_test_nodes.update([host1, host2])
                results[(host1, host2)] = 0.0

    if unpaired:
        log_and_print(f"\nTesting {len(unpaired)} unpaired nodes...")
        for node in unpaired:
            test_partner = None
            for tested in tested_nodes:
                if tested != node and tested not in failed_test_nodes:
                    test_partner = tested
                    break
            if not test_partner:
                for tested in tested_nodes:
                    if tested != node:
                        test_partner = tested
                        break
            if test_partner:
                shape = get_remote_node_shape(node)
                model, config = determine_gpu_model(shape)
                if model:
                    bandwidth = run_nccl_test(test_partner, node, config)
                    if bandwidth is None:
                        failed_test_nodes.add(node)
                        results[(test_partner, node)] = 0.0
                    else:
                        results[(test_partner, node)] = bandwidth
                        tested_nodes.add(node)

    good_nodes = set()
    bad_nodes  = set()
    for (host1, host2), bw in results.items():
        if bw >= global_threshold:
            good_nodes.update([host1, host2])
        elif bw > 0:
            bad_nodes.update([host1, host2])

    all_failed = (timeout_nodes | bad_nodes | failed_test_nodes) - good_nodes
    if all_failed and good_nodes:
        log_and_print("\n=== PARALLEL RETESTING PHASE ===", COLOR_YELLOW)
        retest_results = retest_bad_nodes_with_progress(
            all_failed, good_nodes, default_config, global_threshold,
            reason="comprehensive retest")
        results.update(retest_results)

    final_good_nodes, final_bad_nodes, final_timeout_nodes, all_tested = \
        categorize_nodes_with_timeout_tracking(results, global_threshold)
    print_comprehensive_summary(all_input_nodes, reachable_hosts, final_good_nodes, final_bad_nodes,
                                final_timeout_nodes, unreachable_nodes, global_threshold, results)

def main():
    parser = argparse.ArgumentParser(description="Find bad nodes in the cluster.")
    parser.add_argument('--parallel', action='store_true', help='Run the node check in parallel')
    parser.add_argument('hosts', nargs='*', help='Provide a host file or two host names')
    args = parser.parse_args()
    if args.parallel:
        find_bad_nodes_parallel(args.hosts)
    else:
        find_bad_nodes_serial(args.hosts)

if __name__ == "__main__":
    main()
