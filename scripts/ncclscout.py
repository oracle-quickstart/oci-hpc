#!/usr/bin/env python
###########################
#ncclscout.py – NCCL connectivity & bandwidth diagnostic for OCI Slurm GPU clusters.
#Author: Nuruddin Ahmed
#Date: 2025-12-19
###########################
# How to use this script?
# 1. python3 ncclscout.py hostfile_name --> This is the recommended way to run this script, it will execute nccl bw test sequentially on the hosts given inside the hostfile
# 2. python3 ncclscout.py host1 host2 --> This will test only between two specific nodes
# 3. python3 ncclscout.py --> Wihtout any argument, it will run nccl test between all nodes
# 4. python3 ncclscout.py --parallel (with host_file | with two hosts | without argument) --> --parallel will execute nccl bw tests parallely on 10 host pairs to make the test faster, however, it is not recommended on a production running cluster
##########################
# This tool runs NCCL all-reduce bandwidth tests between node pairs to quickly identify
# unreachable nodes, timeouts, and low-bandwidth “bad” nodes. It automatically detects
# GPU shape/model to apply the correct expected bandwidth threshold, logs full NCCL
# output to nccl_test.log, and writes a readable run summary to nccl_test_screen.log.
#
#Use it before production workloads (or when debugging) to validate multi-node GPU
#communication health across the cluster.
##########################

import subprocess
import os
import sys
import shutil
import concurrent.futures
import uuid
from threading import Lock
import argparse
import itertools
from collections import Counter
from datetime import datetime

# Define supported GPU shapes and their NCCL parameters
GPU_SHAPES = {
    "A100": {"shapes": ["BM.GPU4.8", "BM.GPU.B4.8", "BM.GPU.A100-v2.8"], "threshold": 185.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "H100": {"shapes": ["BM.GPU.H100.8"], "threshold": 440.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "H200": {"shapes": ["BM.GPU.H200.8"], "threshold": 440.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "B200": {"shapes": ["BM.GPU.B200.8"], "threshold": 440.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "B300": {"shapes": ["BM.GPU.B300.8"], "threshold": 750.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"}
}

# ANSI escape codes for colors
COLOR_GREEN = '\033[92m'
COLOR_RED = '\033[91m'
COLOR_YELLOW = '\033[93m'
COLOR_RESET = '\033[0m'

# Log files
NCCL_LOG_FILE = 'nccl_test.log'
SCREEN_LOG_FILE = 'nccl_test_screen.log'

# Global lock for thread-safe logging
log_lock = Lock()

def log_and_print(message, color=""):
    """Print message to screen and log to file"""
    with log_lock:
        # Print to screen with color
        if color:
            print(f"{color}{message}{COLOR_RESET}")
        else:
            print(message)
        
        # Log to file without color codes
        with open(SCREEN_LOG_FILE, 'a') as f:
            f.write(f"{message}\n")

def log_and_print_no_newline(message, color=""):
    """Print message without newline and log to file"""
    with log_lock:
        # Print to screen with color
        if color:
            print(f"{color}{message}{COLOR_RESET}", end='')
        else:
            print(message, end='')
        
        # Log to file without color codes
        with open(SCREEN_LOG_FILE, 'a') as f:
            f.write(message)

# Initialize log file with timestamp
def init_log_files():
    """Initialize log files with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(SCREEN_LOG_FILE, 'a') as f:
        f.write(f"\n{'='*70}\n")
        f.write(f"NCCL Test Started: {timestamp}\n")
        f.write(f"{'='*70}\n")
    
    with open(NCCL_LOG_FILE, 'a') as f:
        f.write(f"\n{'='*70}\n")
        f.write(f"NCCL Test Started: {timestamp}\n")
        f.write(f"{'='*70}\n")

# Ensure the NCCL scripts are executable
def ensure_scripts_executable():
    for config in GPU_SHAPES.values():
        script = config["script"]
        try:
            subprocess.run(['chmod', '+x', script], check=True)
        except subprocess.CalledProcessError as e:
            log_and_print(f"Error setting executable permission for {script}: {e}")

# Copy the node ordering script if the shape is A100
def copy_node_ordering_script():
    source_path = "/opt/oci-hpc/bin/node_ordering_by_rack.py"
    destination_path = "/home/ubuntu/node_ordering_by_rack.py"
    try:
        shutil.copy(source_path, destination_path)
    except FileNotFoundError:
        log_and_print(f"Error: {source_path} not found.")
    except PermissionError:
        log_and_print(f"Error: Permission denied when copying {source_path}.")
    except Exception as e:
        log_and_print(f"Error copying file: {e}")

# Fetch list of Slurm nodes using sinfo.
def get_hosts_from_sinfo():
    try:
        hosts_output = subprocess.check_output(['sinfo', '-N', '-h', '-o', '%N'])
        hosts = [line.strip() for line in hosts_output.decode('utf-8').split('\n') if line.strip()]
        
        # Count duplicates before removing
        host_counts = Counter(hosts)
        duplicates = {host: count for host, count in host_counts.items() if count > 1}
        
        # Remove duplicates while preserving order
        unique_hosts = list(dict.fromkeys(hosts))
        
        if duplicates:
            log_and_print(f"Note: Removed duplicates from sinfo output:")
            for host, count in duplicates.items():
                log_and_print(f"  {host}: appeared {count} times")
            log_and_print(f"Total unique nodes: {len(unique_hosts)}")
        
        return unique_hosts
    except subprocess.CalledProcessError as e:
        log_and_print(f"Error fetching hosts from sinfo: {e}")
        return []
    
def get_hosts_from_file(filename):
    try:
        with open(filename, 'r') as file:
            hosts = [line.strip() for line in file if line.strip()]
            unique_hosts = list(dict.fromkeys(hosts))  # Remove duplicates while preserving order
            if len(unique_hosts) < len(hosts):
                log_and_print(f"Duplicate hosts found and removed, host file updated...")
                with open(filename, 'w') as file:
                    for host in unique_hosts:
                        file.write(f"{host}\n")
            return unique_hosts
    except FileNotFoundError:
        log_and_print(f"Error: Host file '{filename}' not found.")
        return []

# Check if a host is reachable via SSH
def check_host_reachability(host):
    try:
        subprocess.check_call(['ssh', '-o', 'ConnectTimeout=5', host, 'exit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def check_hosts_concurrently(hosts, max_workers=10):
    reachable_hosts = []
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

# Fetch the GPU shape from the remote node.
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

# Determine GPU model, threshold, and NCCL script based on node shape.
def determine_gpu_model(shape):
    for model, config in GPU_SHAPES.items():
        if shape in config["shapes"]:
            return model, config["threshold"], config["script"]
    log_and_print(f"Error: Unrecognized shape '{shape}'.")
    return None, None, None

# Write a temporary hosts file with two nodes.
def write_hosts_file(host1, host2):
    filename = f"hosts_{uuid.uuid4().hex}.txt"
    with open(filename, 'w') as f:
        f.write(f"{host1}\n{host2}\n")
    return filename

# Run the NCCL test between two nodes.
def run_nccl_test(host1, host2, nccl_script, timeout=120):
    # Never test a node with itself
    if host1 == host2:
        log_and_print(f"Error: Cannot test node {host1} with itself")
        return None
        
    hosts_file = write_hosts_file(host1, host2)
    cmd = ['timeout', str(timeout), nccl_script, '1', hosts_file]

    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)

        # Save full output to NCCL log
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

# Helper function to create node pairs for testing
def create_node_pairs(nodes):
    """Create pairs of nodes for testing, ensuring no self-pairing"""
    pairs = []
    unpaired = []
    used = set()
    
    # Create pairs from the list
    i = 0
    while i < len(nodes):
        if i + 1 < len(nodes):
            # Check if next node is different
            if nodes[i] != nodes[i+1]:
                pairs.append((nodes[i], nodes[i+1]))
                used.add(nodes[i])
                used.add(nodes[i+1])
                i += 2
            else:
                # Skip duplicate, add to unpaired
                if nodes[i] not in used:
                    unpaired.append(nodes[i])
                i += 1
        else:
            # Last node if odd number
            if nodes[i] not in used:
                unpaired.append(nodes[i])
            i += 1
    
    # Add any nodes that weren't paired
    for node in nodes:
        if node not in used and node not in unpaired:
            unpaired.append(node)
    
    return pairs, unpaired

# Display a simple progress bar.
def print_progress_bar(iteration, total, prefix='', length=50):
    if total == 0:
        return
    percent = f"{(iteration / total) * 100:.1f}"
    filled_length = int(length * iteration // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    message = f'\r{prefix} |{bar}| {percent}% Complete'
    print(message, end='\r')
    
    # Log progress at key points
    if iteration == total:
        print()
        with open(SCREEN_LOG_FILE, 'a') as f:
            f.write(f"{prefix} completed - {iteration}/{total} (100%)\n")

# Global lock for progress updates
progress_lock = Lock()

# Retest each bad node by pairing it with a known good node
def retest_bad_nodes_with_progress(bad_nodes, good_nodes, nccl_script, threshold, reason="low bandwidth"):
    if not bad_nodes:
        return {}
        
    if not good_nodes:
        log_and_print(f"\nNo good nodes available for retesting bad nodes due to {reason}.", COLOR_RED)
        log_and_print(f"Attempting to find the best among bad nodes...")
        good_nodes = bad_nodes  # Use bad nodes to test against each other

    log_and_print(f"\n\nRetesting {len(bad_nodes)} nodes due to {reason}...")
    retest_results = {}
    total_retests = len(bad_nodes)
    good_nodes_list = list(good_nodes)

    if len(good_nodes_list) < len(bad_nodes):
        log_and_print(f"Note: {len(good_nodes_list)} good node(s) available to test {len(bad_nodes)} bad nodes.", COLOR_YELLOW)

    good_nodes_cycle = itertools.cycle(good_nodes_list)

    for idx, node in enumerate(bad_nodes, 1):
        # Find a different node to test with
        test_partner = None
        attempts = 0
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

        log_and_print_no_newline(f"Retesting {node} with {test_partner}...")
        bandwidth = run_nccl_test(test_partner, node, nccl_script)

        if bandwidth is None:
            log_and_print(f" FAILED", COLOR_RED)
            retest_results[(test_partner, node)] = 0.0
        else:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_YELLOW
            log_and_print(f" {bandwidth:.2f} GB/s", color)
            retest_results[(test_partner, node)] = bandwidth

        print_progress_bar(idx, total_retests, prefix=f'Retesting ({reason})')

    return retest_results

# Helper function for final node categorization
def categorize_nodes_with_timeout_tracking(results, global_threshold):
    """Categorize nodes based on their test results, tracking timeout failures separately"""
    final_good_nodes = set()
    final_bad_nodes = set()
    final_timeout_nodes = set()
    node_test_results = {}
    
    # Collect all test results for each node
    all_tested = set()
    for (host1, host2), bw in results.items():
        all_tested.add(host1)
        all_tested.add(host2)
        
        if host1 not in node_test_results:
            node_test_results[host1] = []
        if host2 not in node_test_results:
            node_test_results[host2] = []
        
        node_test_results[host1].append(bw)
        node_test_results[host2].append(bw)
    
    # Categorize based on best result
    for node, bandwidths in node_test_results.items():
        valid_bws = [bw for bw in bandwidths if bw > 0]
        
        if valid_bws:
            best_bw = max(valid_bws)
            if best_bw >= global_threshold:
                final_good_nodes.add(node)
            else:
                final_bad_nodes.add(node)
        else:
            # All tests failed
            final_bad_nodes.add(node)
            final_timeout_nodes.add(node)
    
    return final_good_nodes, final_bad_nodes, final_timeout_nodes, all_tested

# Print comprehensive summary
def print_comprehensive_summary(all_input_nodes, reachable_hosts, final_good_nodes, final_bad_nodes, 
                               final_timeout_nodes, unreachable_nodes, global_threshold, results):
    """Print a comprehensive summary of all node states"""
    
    log_and_print("\n" + "="*70)
    log_and_print("COMPREHENSIVE NODE ACCOUNTING SUMMARY")
    log_and_print("="*70)
    log_and_print(f"\nTotal nodes provided: {len(all_input_nodes)}")
    log_and_print(f"├── Reachable nodes: {len(set(reachable_hosts))}")
    log_and_print(f"│   └── Successfully categorized: {len(final_good_nodes) + len(final_bad_nodes)}")
    
    # Good nodes - green only if there are good nodes
    if final_good_nodes:
        log_and_print(f"│       ├── Good nodes (≥ {global_threshold} GB/s): {len(final_good_nodes)}", COLOR_GREEN)
    else:
        log_and_print(f"│       ├── Good nodes (≥ {global_threshold} GB/s): 0")
    
    # Bad nodes - red only if there are bad nodes
    if final_bad_nodes:
        log_and_print(f"│       └── Bad nodes (< {global_threshold} GB/s or failed): {len(final_bad_nodes)}", COLOR_RED)
        
        # Failed all tests - red only if there are such nodes
        if final_timeout_nodes:
            log_and_print(f"│           └── Failed all tests (timeout/error): {len(final_timeout_nodes)}", COLOR_RED)
    else:
        log_and_print(f"│       └── Bad nodes (< {global_threshold} GB/s or failed): 0")
    
    # Unreachable nodes - red only if there are unreachable nodes
    if unreachable_nodes:
        log_and_print(f"└── Unreachable nodes: {len(unreachable_nodes)}", COLOR_RED)
    else:
        log_and_print(f"└── Unreachable nodes: 0")
    
    # Verify accounting
    total_accounted = len(final_good_nodes) + len(final_bad_nodes) + len(unreachable_nodes)
    
    log_and_print(f"\nVerification: {total_accounted} nodes accounted for out of {len(all_input_nodes)} total")
    
    if total_accounted != len(all_input_nodes):
        log_and_print(f"WARNING: Node count mismatch!", COLOR_RED)
        unaccounted = all_input_nodes - final_good_nodes - final_bad_nodes - unreachable_nodes
        if unaccounted:
            log_and_print(f"Unaccounted nodes: {', '.join(sorted(unaccounted))}")

    # Detailed breakdowns
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
    
    # Performance statistics
    valid_bandwidths = [bw for bw in results.values() if bw > 0]
    if valid_bandwidths:
        log_and_print(f"\nBandwidth Statistics:")
        log_and_print(f"  Maximum: {max(valid_bandwidths):.2f} GB/s")
        log_and_print(f"  Minimum: {min(valid_bandwidths):.2f} GB/s")
        log_and_print(f"  Average: {sum(valid_bandwidths)/len(valid_bandwidths):.2f} GB/s")
        
        failed_tests = sum(1 for bw in results.values() if bw == 0.0)
        if failed_tests:
            log_and_print(f"  Failed tests: {failed_tests}")
    
    if final_bad_nodes or unreachable_nodes:
        log_and_print(f"\nPlease perform health checks on problematic nodes.", COLOR_YELLOW)
    
    # Log summary to file
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_and_print(f"\nTest completed at: {timestamp}")

# Main function - Serial version
def find_bad_nodes_serial(hosts):
    init_log_files()
    ensure_scripts_executable()
    copy_node_ordering_script()

    # Initialize tracking sets
    all_input_nodes = set()
    unreachable_nodes = set()
    tested_nodes = set()
    failed_test_nodes = set()
    timeout_nodes = set()

    # Get hosts based on input
    if len(hosts) == 0:
        hosts = get_hosts_from_sinfo()
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL test on {len(hosts)} unique nodes from sinfo...")
    elif len(hosts) == 1:
        hosts = get_hosts_from_file(hosts[0])
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL test on {len(hosts)} nodes from file...")
    elif len(hosts) == 2:
        # Test between two specific nodes
        host1, host2 = hosts[0], hosts[1]
        
        if host1 == host2:
            log_and_print(f"Error: Cannot test a node with itself ({host1})", COLOR_RED)
            return
            
        log_and_print(f"Running NCCL test between: {host1} and {host2}...")
        shape = get_remote_node_shape(host1)
        if not shape:
            log_and_print(f"Unable to fetch node shape from {host1}. Exiting.")
            return

        gpu_model, threshold, nccl_script = determine_gpu_model(shape)
        if not gpu_model:
            return

        bandwidth = run_nccl_test(host1, host2, nccl_script, timeout=60)
        if bandwidth is not None:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_RED
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

    # Check reachability
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

    # Create test pairs
    log_and_print("\nCreating test pairs...")
    test_pairs, unpaired = create_node_pairs(reachable_hosts)
    
    log_and_print(f"Created {len(test_pairs)} test pairs")
    if unpaired:
        log_and_print(f"Unpaired nodes ({len(unpaired)}): {', '.join(unpaired)}")

    results = {}
    global_threshold = None
    default_script = "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"
    
    # Run initial tests
    log_and_print("\nRunning NCCL Tests sequentially...")
    for i, (host1, host2) in enumerate(test_pairs, 1):
        shape1 = get_remote_node_shape(host1)
        shape2 = get_remote_node_shape(host2)

        model1, threshold1, script1 = determine_gpu_model(shape1)
        model2, threshold2, script2 = determine_gpu_model(shape2)

        if not model1 or not model2:
            log_and_print(f"Skipping pair {host1}-{host2} - unrecognized shape")
            continue

        threshold = min(threshold1, threshold2)
        if global_threshold is None:
            global_threshold = threshold
        
        script = script1
        default_script = script

        log_and_print_no_newline(f"Testing {host1} <-> {host2}...")
        bandwidth = run_nccl_test(host1, host2, script)

        if bandwidth is None:
            log_and_print(f" FAILED", COLOR_RED)
            failed_test_nodes.update([host1, host2])
            timeout_nodes.update([host1, host2])
            results[(host1, host2)] = 0.0
        else:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_YELLOW
            log_and_print(f" {bandwidth:.2f} GB/s", color)
            results[(host1, host2)] = bandwidth
            tested_nodes.update([host1, host2])

        print_progress_bar(i, len(test_pairs), prefix='Testing pairs')

    # ALWAYS test unpaired nodes
    if unpaired:
        log_and_print(f"\n\nTesting {len(unpaired)} unpaired nodes...")
        for node in unpaired:
            # Find the best available node to test with
            test_partner = None
            
            # First, try to find a good node
            for tested in tested_nodes:
                if tested != node and tested not in failed_test_nodes:
                    test_partner = tested
                    break
            
            # If no good node, try any tested node
            if not test_partner:
                for tested in tested_nodes:
                    if tested != node:
                        test_partner = tested
                        break
            
            # If still no partner, use first available different node
            if not test_partner:
                for candidate in reachable_hosts:
                    if candidate != node:
                        test_partner = candidate
                        break
            
            if test_partner:
                shape = get_remote_node_shape(node)
                model, threshold, script = determine_gpu_model(shape)
                
                if model:
                    log_and_print_no_newline(f"Testing unpaired node {node} with {test_partner}...")
                    bandwidth = run_nccl_test(test_partner, node, script)
                    
                    if bandwidth is None:
                        log_and_print(f" FAILED", COLOR_RED)
                        failed_test_nodes.add(node)
                        timeout_nodes.add(node)
                        results[(test_partner, node)] = 0.0
                    else:
                        color = COLOR_GREEN if bandwidth >= (global_threshold or threshold) else COLOR_YELLOW
                        log_and_print(f" {bandwidth:.2f} GB/s", color)
                        results[(test_partner, node)] = bandwidth
                        tested_nodes.add(node)
            else:
                log_and_print(f"Warning: Could not find any partner to test {node}", COLOR_RED)
                failed_test_nodes.add(node)
                results[(node, node)] = 0.0

    # Set default threshold if needed
    if global_threshold is None:
        global_threshold = 185.0

    # Print initial results
    log_and_print("\n\nInitial Test Results:")
    for (host1, host2), bandwidth in sorted(results.items(), key=lambda x: x[1], reverse=True):
        if bandwidth > 0:
            color = COLOR_GREEN if bandwidth >= global_threshold else COLOR_RED
            log_and_print(f"  {host1} <-> {host2}: {bandwidth:.2f} GB/s", color)
        else:
            log_and_print(f"  {host1} <-> {host2}: FAILED", COLOR_RED)

    # Determine good/bad nodes for retesting
    good_nodes = set()
    bad_nodes = set()
    
    for (host1, host2), bw in results.items():
        if bw >= global_threshold:
            good_nodes.update([host1, host2])
        elif bw > 0:
            bad_nodes.update([host1, host2])

    bad_nodes = bad_nodes - good_nodes

    # COMPREHENSIVE RETESTING
    all_failed_nodes = timeout_nodes | bad_nodes | failed_test_nodes
    all_failed_nodes = all_failed_nodes - good_nodes
    
    if all_failed_nodes:
        log_and_print(f"\n=== COMPREHENSIVE RETESTING PHASE ===", COLOR_YELLOW)
        log_and_print(f"Retesting all {len(all_failed_nodes)} problematic nodes...")
        
        # First retest with good nodes if available
        if good_nodes:
            log_and_print("\nPhase 1: Retesting with confirmed good nodes...")
            retest_results = retest_bad_nodes_with_progress(
                all_failed_nodes, good_nodes, default_script, global_threshold, reason="comprehensive check"
            )
            results.update(retest_results)
            
            # Update good/bad nodes based on retest
            for (host1, host2), bw in retest_results.items():
                if bw >= global_threshold:
                    good_nodes.update([host1, host2])
                    all_failed_nodes.discard(host1)
                    all_failed_nodes.discard(host2)
        
        # Second phase: remaining bad nodes test with each other
        remaining_bad = all_failed_nodes - good_nodes
        if remaining_bad and len(remaining_bad) > 1:
            log_and_print("\nPhase 2: Cross-testing remaining problematic nodes...")
            bad_list = list(remaining_bad)
            bad_pairs = []
            for i in range(len(bad_list)):
                for j in range(i+1, len(bad_list)):
                    bad_pairs.append((bad_list[i], bad_list[j]))
            
            # Test first few pairs
            for idx, (node1, node2) in enumerate(bad_pairs[:min(10, len(bad_pairs))], 1):
                log_and_print_no_newline(f"Cross-test {node1} <-> {node2}...")
                bandwidth = run_nccl_test(node1, node2, default_script)
                
                if bandwidth is None:
                    log_and_print(f" FAILED", COLOR_RED)
                    results[(node1, node2)] = 0.0
                else:
                    color = COLOR_GREEN if bandwidth >= global_threshold else COLOR_YELLOW
                    log_and_print(f" {bandwidth:.2f} GB/s", color)
                    results[(node1, node2)] = bandwidth
                    
                    if bandwidth >= global_threshold:
                        good_nodes.update([node1, node2])

    # Final categorization
    final_good_nodes, final_bad_nodes, final_timeout_nodes, all_tested = categorize_nodes_with_timeout_tracking(results, global_threshold)
    
    # Print summary
    print_comprehensive_summary(all_input_nodes, reachable_hosts, final_good_nodes, final_bad_nodes,
                               final_timeout_nodes, unreachable_nodes, global_threshold, results)

# Main function - Parallel version
def find_bad_nodes_parallel(hosts):
    init_log_files()
    ensure_scripts_executable()
    copy_node_ordering_script()

    # Initialize tracking sets
    all_input_nodes = set()
    unreachable_nodes = set()
    tested_nodes = set()
    failed_test_nodes = set()
    timeout_nodes = set()

    # Get hosts based on input
    if len(hosts) == 0:
        hosts = get_hosts_from_sinfo()
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL test on {len(hosts)} unique nodes from sinfo...")
    elif len(hosts) == 1:
        hosts = get_hosts_from_file(hosts[0])
        all_input_nodes = set(hosts)
        log_and_print(f"Running NCCL test on {len(hosts)} nodes from file...")
    elif len(hosts) == 2:
        host1, host2 = hosts[0], hosts[1]
        
        if host1 == host2:
            log_and_print(f"Error: Cannot test a node with itself ({host1})", COLOR_RED)
            return
            
        log_and_print(f"Running NCCL test between: {host1} and {host2}...")
        shape = get_remote_node_shape(host1)
        if not shape:
            log_and_print(f"Unable to fetch node shape from {host1}. Exiting.")
            return

        gpu_model, threshold, nccl_script = determine_gpu_model(shape)
        if not gpu_model:
            return

        bandwidth = run_nccl_test(host1, host2, nccl_script, timeout=120)
        if bandwidth is not None:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_RED
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

    # Check reachability
    log_and_print(f"\nChecking reachability of {len(hosts)} nodes...")
    reachable_hosts, unreachable_list = check_hosts_concurrently(hosts)
    unreachable_nodes = set(unreachable_list)
    
    if unreachable_nodes:
        log_and_print(f"\nWarning: {len(unreachable_nodes)} nodes are unreachable and will be excluded from testing.", COLOR_RED)
    
    if len(reachable_hosts) < 2:
        log_and_print("Not enough reachable hosts to proceed.")
        return

    # Create test pairs
    test_pairs, unpaired = create_node_pairs(reachable_hosts)
    log_and_print(f"Created {len(test_pairs)} test pairs for parallel testing")
    if unpaired:
        log_and_print(f"Unpaired nodes to test separately: {', '.join(unpaired)}")

    # Prepare pairs for parallel execution
    pairs_to_test = []
    thresholds = {}
    global_threshold = None
    default_script = "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"

    for host1, host2 in test_pairs:
        shape1 = get_remote_node_shape(host1)
        shape2 = get_remote_node_shape(host2)

        model1, threshold1, script1 = determine_gpu_model(shape1)
        model2, threshold2, script2 = determine_gpu_model(shape2)

        if not model1 or not model2:
            continue

        threshold = min(threshold1, threshold2)
        if global_threshold is None:
            global_threshold = threshold
            default_script = script1
            
        thresholds[(host1, host2)] = threshold
        pairs_to_test.append((host1, host2, script1))

    # Set default threshold if none found
    if global_threshold is None:
        global_threshold = 185.0

    # Run tests in parallel
    log_and_print("\nRunning NCCL Tests in parallel...")
    results = {}

    with concurrent.futures.ProcessPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(run_nccl_test, *pair): pair for pair in pairs_to_test}

        for future in concurrent.futures.as_completed(futures):
            host1, host2, _ = futures[future]
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
                    color = COLOR_GREEN if bandwidth >= threshold else COLOR_YELLOW
                    log_and_print(f"{host1} <-> {host2}: {bandwidth:.2f} GB/s", color)
            except Exception as e:
                log_and_print(f"Error in parallel test for {host1} <-> {host2}: {e}")
                failed_test_nodes.update([host1, host2])
                results[(host1, host2)] = 0.0

    # Handle unpaired nodes
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
                model, threshold, script = determine_gpu_model(shape)
                
                if model:
                    bandwidth = run_nccl_test(test_partner, node, script)
                    if bandwidth is None:
                        failed_test_nodes.add(node)
                        results[(test_partner, node)] = 0.0
                    else:
                        results[(test_partner, node)] = bandwidth
                        tested_nodes.add(node)

    # Categorize initial results
    good_nodes = set()
    bad_nodes = set()
    
    for (host1, host2), bw in results.items():
        if bw >= global_threshold:
            good_nodes.update([host1, host2])
        elif bw > 0:
            bad_nodes.update([host1, host2])

    # Comprehensive retesting
    all_failed = (timeout_nodes | bad_nodes | failed_test_nodes) - good_nodes
    
    if all_failed and good_nodes:
        log_and_print(f"\n=== PARALLEL RETESTING PHASE ===", COLOR_YELLOW)
        retest_results = retest_bad_nodes_with_progress(
            all_failed, good_nodes, default_script, global_threshold, reason="comprehensive retest"
        )
        results.update(retest_results)

    # Final categorization
    final_good_nodes, final_bad_nodes, final_timeout_nodes, all_tested = categorize_nodes_with_timeout_tracking(results, global_threshold)
    
    # Print summary
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