#!/usr/bin/env python

###########################
# How to use this script?
# 1. python3 ncclscout.py hostfile_name --> This is the recommended way to run this script, it will execute nccl bw test sequentially on the hosts given inside the hostfile
# 2. python3 ncclscout.py host1 host2 --> This will test only between two specific nodes
# 3. python3 ncclscout.py --> Wihtout any argument, it will run nccl test between all nodes
# 4. python3 ncclscout.py --parallel (with host_file | with two hosts | without argument) --> --parallel will execute nccl bw tests parallely on 10 host pairs to make the test faster, however, it is not recommended on a production running cluster
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

# Define supported GPU shapes and their NCCL parameters
GPU_SHAPES = {
    "A100": {"shapes": ["BM.GPU4.8", "BM.GPU.B4.8", "BM.GPU.A100-v2.8"], "threshold": 185.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"},
    "H100": {"shapes": ["BM.GPU.H100.8"], "threshold": 440.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce_H100_200.sh"},
    "H200": {"shapes": ["BM.GPU.H200.8"], "threshold": 440.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce_H100_200.sh"},
    "B200": {"shapes": ["BM.GPU.B200.8"], "threshold": 440.0, "script": "/opt/oci-hpc/samples/gpu/nccl_run_allreduce_H100_200.sh"}
}

# ANSI escape codes for colors
COLOR_GREEN = '\033[92m'
COLOR_RED = '\033[91m'
COLOR_YELLOW = '\033[93m'
COLOR_RESET = '\033[0m'

# Log files and backup directory
NCCL_LOG_FILE = 'nccl_test.log'

# Ensure the NCCL scripts are executable
def ensure_scripts_executable():
    for config in GPU_SHAPES.values():
        script = config["script"]
        try:
            subprocess.run(['chmod', '+x', script], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error setting executable permission for {script}: {e}")

# Copy the node ordering script if the shape is A100
def copy_node_ordering_script():
    source_path = "/opt/oci-hpc/bin/node_ordering_by_rack.py"
    destination_path = "/home/ubuntu/node_ordering_by_rack.py"
    try:
        shutil.copy(source_path, destination_path)
    except FileNotFoundError:
        print(f"Error: {source_path} not found.")
    except PermissionError:
        print(f"Error: Permission denied when copying {source_path}.")
    except Exception as e:
        print(f"Error copying file: {e}")

# Fetch list of Slurm nodes using sinfo.
def get_hosts_from_sinfo():
    try:
        hosts_output = subprocess.check_output(['sinfo', '-N', '-h', '-o', '%N'])
        return [line.strip() for line in hosts_output.decode('utf-8').split('\n') if line.strip()]
    except subprocess.CalledProcessError as e:
        print(f"Error fetching hosts from sinfo: {e}")
        return []
    
def get_hosts_from_file(filename):
    try:
        with open(filename, 'r') as file:
            hosts = [line.strip() for line in file if line.strip()]
            unique_hosts = list(dict.fromkeys(hosts))  # Remove duplicates while preserving order
            if len(unique_hosts) < len(hosts):
                print(f"Duplicate hosts found and removed, host file updated...")
                with open(filename, 'w') as file:
                    for host in unique_hosts:
                        file.write(f"{host}\n")
            return unique_hosts
    except FileNotFoundError:
        print(f"Error: Host file '{filename}' not found.")
        return []

# Check if a host is reachable via SSH
def check_host_reachability(host):
    try:
        subprocess.check_call(['ssh', '-o', 'ConnectTimeout=5', host, 'exit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        print(f"Host {host} is unreachable.")
        return False

def check_hosts_concurrently(hosts, max_workers=10):
    reachable_hosts = []

    def check_and_return(host):
        if check_host_reachability(host):
            return host
        return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(check_and_return, host): host for host in hosts}

        for future in concurrent.futures.as_completed(futures):
            host = futures[future]
            try:
                result = future.result()
                if result:
                    reachable_hosts.append(result)
            except Exception as e:
                print(f"Error checking host {host}: {e}")

    return reachable_hosts

# Fetch the GPU shape from the remote node.
def get_remote_node_shape(node):
    try:
        cmd = (
            f'ssh {node} '
            f'"curl -sH \\"Authorization: Bearer Oracle\\" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape"'
        )
        return subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
    except subprocess.CalledProcessError as e:
        print(f"Error fetching node shape from {node}: {e}")
        return None

# Determine GPU model, threshold, and NCCL script based on node shape.
def determine_gpu_model(shape):
    for model, config in GPU_SHAPES.items():
        if shape in config["shapes"]:
            return model, config["threshold"], config["script"]
    print(f"Error: Unrecognized shape '{shape}'.")
    return None, None, None

# Write a temporary hosts file with two nodes.
def write_hosts_file(host1, host2):
    filename = f"hosts_{uuid.uuid4().hex}.txt"
    with open(filename, 'w') as f:
        f.write(f"{host1}\n{host2}\n")
    return filename

# Run the NCCL test between two nodes.
def run_nccl_test(host1, host2, nccl_script, timeout=120):
    hosts_file = write_hosts_file(host1, host2)
    cmd = ['timeout', str(timeout), nccl_script, '1', hosts_file]

    try:
        output = subprocess.check_output(cmd)

        # Save full output to log
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
            print(f"Warning: No valid bandwidth data for {host1} and {host2}. Full output logged.")
            return float(0)

        return float(valid_line.split()[-2])
    except subprocess.TimeoutExpired:
        print(f"Error: NCCL test timed out for pair {host1} and {host2}.")
    except subprocess.CalledProcessError as e:
        print(f"Error running NCCL test between {host1} and {host2}: {e}")
    except ValueError as e:
        print(f"Error parsing bandwidth output for {host1} and {host2}: {e}")
    finally:
        if os.path.exists(hosts_file):
            os.remove(hosts_file)
    return None

# Display a simple progress bar.
def print_progress_bar(iteration, total, prefix='', length=50):
    percent = f"{(iteration / total) * 100:.1f}"
    filled_length = int(length * iteration // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    print(f'\r{prefix} |{bar}| {percent}% Complete', end='\r')
    if iteration == total:
        print()

# Global lock for progress updates
progress_lock = Lock()

# Update progress in the main process
def update_progress(progress_tracker):
    with progress_lock:
        progress_tracker['completed'] += 1
        print_progress_bar(progress_tracker['completed'], progress_tracker['total'], prefix='Testing pairs')

# Retest each bad node by pairing it with a known good node (Sequential with progress bar)
def retest_bad_nodes_with_progress(bad_nodes, good_nodes, nccl_script, reason="low bandwidth"):
    if not good_nodes:
        print(f"\n{COLOR_RED}No good nodes available for retesting bad nodes due to {reason}. Retesting with existing bad nodes to find the best.{COLOR_RESET}")
        good_nodes = bad_nodes.copy()  # If no good nodes, try using bad nodes themselves for testing

    print(f"\n\nRetesting bad nodes due to {reason} with available good nodes...")
    retest_results = {}
    total_retests = len(bad_nodes)
    good_nodes_list = list(good_nodes)

    # Notify if only a few good nodes exist
    if len(good_nodes_list) < len(bad_nodes):
        print(f"\n{COLOR_YELLOW}There are {len(good_nodes_list)} good node(s) to retest {len(bad_nodes)} bad nodes. Reusing good nodes as needed.{COLOR_RESET}")

    good_nodes_cycle = itertools.cycle(good_nodes_list)  # Cycle through available good nodes

    for idx, node in enumerate(bad_nodes, 1):
        good_node = next(good_nodes_cycle)  # Always use a different good node first
        
        # Ensure a node does not test itself
        while good_node == node and len(good_nodes_list) > 1:
            good_node = next(good_nodes_cycle)  # Pick a different node

        print(f"Retesting NCCL test between {good_node} and {node}...", end='')
        bandwidth = run_nccl_test(good_node, node, nccl_script)

        if bandwidth is None:
            print(f"\n{COLOR_RED}Retest failed for {node}. Marking as bad.{COLOR_RESET}")
        else:
            retest_results[(good_node, node)] = bandwidth

        print_progress_bar(idx, total_retests, prefix=f'Retesting pairs ({reason})')

    return retest_results

# Main function to find and report bad nodes based on NCCL test results. (Serial)
def find_bad_nodes_serial(hosts):
    ensure_scripts_executable()
    copy_node_ordering_script()

    if len(hosts) == 0:
        hosts = get_hosts_from_sinfo()
        print("Running NCCL test on hosts from sinfo...")
    elif len(hosts) == 1:
        hosts = get_hosts_from_file(hosts[0])
        print(f"Running NCCL test on hosts from the given file...")
    elif len(hosts) == 2:
        host1, host2 = hosts[0], hosts[1]
        print(f"Running NCCL test between: {host1} and {host2}...")

        shape = get_remote_node_shape(host1)
        if not shape:
            print(f"Unable to fetch node shape from {host1}. Exiting.")
            return

        gpu_model, threshold, nccl_script = determine_gpu_model(shape)
        if not gpu_model:
            return

        bandwidth = run_nccl_test(host1, host2, nccl_script, timeout=60)
        if bandwidth is not None:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_RED
            print(f"\nResult: {host1} <-> {host2}: {color}{bandwidth:.2f} GB/s{COLOR_RESET}")
        return
    else:
        print("Usage: script.py [host_file | host1 host2]")
        return

    if not hosts:
        print("No hosts found.")
        return

    print("\nChecking host reachability...")
    reachable_hosts = check_hosts_concurrently(hosts)
    if len(reachable_hosts) < 2:
        print("Not enough reachable hosts to proceed.")
        return

    results = {}
    timeout_nodes = set()
    print("\nRunning NCCL Tests sequentially...")
    total_pairs = len(reachable_hosts) // 2

    for i, (host1, host2) in enumerate(zip(reachable_hosts[::2], reachable_hosts[1::2]), 1):
        shape1 = get_remote_node_shape(host1)
        shape2 = get_remote_node_shape(host2)

        model1, threshold1, script1 = determine_gpu_model(shape1)
        model2, threshold2, script2 = determine_gpu_model(shape2)

        if not model1 or not model2:
            print(f"Skipping test between {host1} and {host2} due to unrecognized GPU shape.")
            continue

        threshold = min(threshold1, threshold2)
        script = script1 if script1 == script2 else script1

        print(f"Running NCCL test between {host1} and {host2}...", end='')
        bandwidth = run_nccl_test(host1, host2, script)

        if bandwidth is None:
            timeout_nodes.add(host2)  # Track timeouts
        else:
            results[(host1, host2)] = bandwidth  # Store valid results

        print_progress_bar(i, total_pairs, prefix='Testing pairs')

    # Handle the last node if the number of nodes is odd.
    if len(reachable_hosts) % 2 == 1:
        last_node = reachable_hosts[-1]
        known_good_node = reachable_hosts[0]  # Use the first good node available
        print(f"\nRunning NCCL test for the last unpaired node: {last_node} with {known_good_node}...", end='')
        bandwidth = run_nccl_test(known_good_node, last_node, script1)
        if bandwidth is not None:
            results[(known_good_node, last_node)] = bandwidth
        else:
            timeout_nodes.add(last_node)  # If it fails, mark it as timeout

    print("\n\nInitial NCCL Test Results:")
    for (host1, host2), bandwidth in sorted(results.items(), key=lambda x: x[1], reverse=True):
        threshold = min(determine_gpu_model(get_remote_node_shape(host1))[1],
                        determine_gpu_model(get_remote_node_shape(host2))[1])
        color = COLOR_GREEN if bandwidth >= threshold else COLOR_RED
        print(f"({host1}, {host2}): {color}{bandwidth:.2f} GB/s{COLOR_RESET}")

    good_nodes = {host for pair, bw in results.items() if bw >= threshold for host in pair}
    bad_nodes = {host for pair, bw in results.items() if bw < threshold for host in pair}

    # Retest nodes that failed due to timeout.
    timeout_retest_results = {}
    if good_nodes and timeout_nodes:
        timeout_retest_results = retest_bad_nodes_with_progress(timeout_nodes, good_nodes, script1, reason="timeout")
        results.update(timeout_retest_results)

    # Retest nodes that failed due to low bandwidth.
    low_bw_retest_results = {}
    if good_nodes and bad_nodes:
        low_bw_retest_results = retest_bad_nodes_with_progress(bad_nodes, good_nodes, script1, reason="low bandwidth")
        results.update(low_bw_retest_results)

    # Retest Summary for Timeout Failures.
    if timeout_retest_results:
        print("\nRetest Results for Timeout Failures:")
        for (good_node, bad_node), bw in timeout_retest_results.items():
            threshold = min(determine_gpu_model(get_remote_node_shape(good_node))[1],
                            determine_gpu_model(get_remote_node_shape(bad_node))[1])
            color = COLOR_GREEN if bw >= threshold else COLOR_RED
            print(f"Retest between {good_node} and {bad_node}: {color}{bw:.2f} GB/s{COLOR_RESET}")

    # Retest Summary for Low Bandwidth Failures.
    if low_bw_retest_results:
        print("\nRetest Results for Low Bandwidth Failures:")
        for (good_node, bad_node), bw in low_bw_retest_results.items():
            threshold = min(determine_gpu_model(get_remote_node_shape(good_node))[1],
                            determine_gpu_model(get_remote_node_shape(bad_node))[1])
            color = COLOR_GREEN if bw >= threshold else COLOR_RED
            print(f"Retest between {good_node} and {bad_node}: {color}{bw:.2f} GB/s{COLOR_RESET}")

    # Finalize Good & Bad Node Lists.
    final_good_nodes = {host for pair, bw in results.items() if bw >= threshold for host in pair}
    final_bad_nodes = {host for pair, bw in results.items() if bw < threshold for host in pair}
    confirmed_bad_nodes = {node for node in final_bad_nodes if node not in final_good_nodes}

    print("\nSummary:")
    print(f"\nGood Bandwidth Pairs (≥ threshold): {len([bw for bw in results.values() if bw >= threshold])}")
    print(f"Bad Bandwidth Pairs (< threshold): {len([bw for bw in results.values() if bw < threshold])}")
    print(f"\nTotal Good Nodes: {len(final_good_nodes)}")
    print("   ", ", ".join(sorted(final_good_nodes)))
    print(f"\nTotal Bad Nodes: {len(confirmed_bad_nodes)}")
    print("   ", ", ".join(sorted(confirmed_bad_nodes)))
    print(f"\nMaximum Bandwidth: {max(results.values()) if results else 0.0} GB/s")
    print(f"Minimum Bandwidth: {min(results.values()) if results else 0.0} GB/s")
    print("Please perform healtchchecks if there are any bad node(s).")

# Main function to find and report bad nodes based on NCCL test results. (Parallel)
def find_bad_nodes_parallel(hosts):
    ensure_scripts_executable()
    copy_node_ordering_script()

    # Handle input options
    if len(hosts) == 0:
        hosts = get_hosts_from_sinfo()
        print(f"Running NCCL test on hosts from sinfo...")
    elif len(hosts) == 1:
        hosts = get_hosts_from_file(hosts[0])
        print(f"Running NCCL test on hosts from the given host file...")
    elif len(hosts) == 2:
        host1, host2 = hosts[0], hosts[1]
        print(f"Running NCCL test only between: {host1} and {host2}...")

        shape = get_remote_node_shape(host1)
        if not shape:
            print(f"Unable to fetch node shape from {host1}. Exiting.")
            return

        gpu_model, threshold, nccl_script = determine_gpu_model(shape)
        if not gpu_model:
            return

        bandwidth = run_nccl_test(host1, host2, nccl_script, timeout=120)
        if bandwidth is not None:
            color = COLOR_GREEN if bandwidth >= threshold else COLOR_RED
            print(f"\nResult: {host1} <-> {host2}: {color}{bandwidth:.2f} GB/s{COLOR_RESET}")
        return
    else:
        print("Usage: script.py [host_file | host1 host2]")
        return

    if not hosts:
        print("No hosts found.")
        return

    # Check host reachability
    print("\nChecking host reachability...")
    reachable_hosts = check_hosts_concurrently(hosts)
    if len(reachable_hosts) < 2:
        print("Not enough reachable hosts to proceed.")
        return

    # Prepare test pairs
    pairs_to_test, thresholds = [], {}
    for host1, host2 in zip(reachable_hosts[::2], reachable_hosts[1::2]):
        shape1 = get_remote_node_shape(host1)
        shape2 = get_remote_node_shape(host2)

        model1, threshold1, script1 = determine_gpu_model(shape1)
        model2, threshold2, script2 = determine_gpu_model(shape2)

        if not model1 or not model2:
            print(f"Skipping test between {host1} and {host2} due to unrecognized GPU shape.")
            continue

        threshold = min(threshold1, threshold2)
        thresholds[(host1, host2)] = threshold
        pairs_to_test.append((host1, host2, script1))

    # Handle the last node if the number of nodes is odd
    if len(reachable_hosts) % 2 == 1:
        last_node = reachable_hosts[-1]
        known_good_node = reachable_hosts[0]
        if (known_good_node, last_node) not in pairs_to_test:
            pairs_to_test.append((known_good_node, last_node, script1))

    # Start parallel testing
    print("\nRunning NCCL Tests in parallel...")
    results = {}
    timeout_nodes = set()

    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(run_nccl_test, *pair): pair for pair in pairs_to_test}

        for future in concurrent.futures.as_completed(futures):
            host1, host2, _ = futures[future]
            try:
                bandwidth = future.result()
                if bandwidth is None:
                    timeout_nodes.update([host1, host2])  # Track timeout failures
                else:
                    results[(host1, host2)] = bandwidth
            except Exception as e:
                print(f"Error running NCCL test for pair ({host1}, {host2}): {e}")

    # Print Initial NCCL Test Results
    print("\n\nInitial NCCL Test Results:")
    good_nodes, bad_nodes = set(), set()
    for (host1, host2), bandwidth in sorted(results.items(), key=lambda x: x[1], reverse=True):
        threshold = thresholds.get((host1, host2), 0)
        color = COLOR_GREEN if bandwidth >= threshold else COLOR_RED
        print(f"({host1}, {host2}): {color}{bandwidth:.2f} GB/s{COLOR_RESET}")

        if bandwidth >= threshold:
            good_nodes.update([host1, host2])
        else:
            bad_nodes.update([host1, host2])

    # Retest nodes that failed due to timeout.
    timeout_retest_results = {}
    if good_nodes and timeout_nodes:
        timeout_retest_results = retest_bad_nodes_with_progress(timeout_nodes, good_nodes, script1, reason="timeout")
        results.update(timeout_retest_results)

    # Retest nodes that failed due to low bandwidth.
    low_bw_retest_results = {}
    if good_nodes and bad_nodes:
        bad_nodes_for_retest = {node for node in bad_nodes if node not in good_nodes}
        if bad_nodes_for_retest:
            low_bw_retest_results = retest_bad_nodes_with_progress(bad_nodes_for_retest, good_nodes, script1, reason="low bandwidth")
            results.update(low_bw_retest_results)

    # Retest Summary for Timeout Failures.
    if timeout_retest_results:
        print("\nRetest Results for Timeout Failures:")
        for (good_node, bad_node), bw in timeout_retest_results.items():
            threshold = min(thresholds.get((good_node, bad_node), 0), thresholds.get((bad_node, good_node), 0))
            color = COLOR_GREEN if bw >= threshold else COLOR_RED
            print(f"Retest between {good_node} and {bad_node}: {color}{bw:.2f} GB/s{COLOR_RESET}")

    # Retest Summary for Low Bandwidth Failures.
    if low_bw_retest_results:
        print("\nRetest Results for Low Bandwidth Failures:")
        for (good_node, bad_node), bw in low_bw_retest_results.items():
            threshold = min(thresholds.get((good_node, bad_node), 0), thresholds.get((bad_node, good_node), 0))
            color = COLOR_GREEN if bw >= threshold else COLOR_RED
            print(f"Retest between {good_node} and {bad_node}: {color}{bw:.2f} GB/s{COLOR_RESET}")

    # Finalize Good & Bad Node Lists.
    final_good_nodes = {host for pair, bw in results.items() if bw >= thresholds.get(pair, 0) for host in pair}
    final_bad_nodes = {host for pair, bw in results.items() if bw < thresholds.get(pair, 0) for host in pair}
    confirmed_bad_nodes = {node for node in final_bad_nodes if node not in final_good_nodes}

    # Print Summary
    print("\nSummary:")
    print(f"\nGood Bandwidth Pairs (≥ threshold): {len([bw for bw in results.values() if bw >= min(thresholds.values())])}")
    print(f"Bad Bandwidth Pairs (< threshold): {len([bw for bw in results.values() if bw < min(thresholds.values())])}")
    print(f"\nTotal Good Nodes: {len(final_good_nodes)}")
    print("   ", ", ".join(sorted(final_good_nodes)))
    print(f"\nTotal Bad Nodes: {len(confirmed_bad_nodes)}")
    print("   ", ", ".join(sorted(confirmed_bad_nodes)))
    print(f"\nMaximum Bandwidth: {max(results.values()) if results else 0.0} GB/s")
    print(f"Minimum Bandwidth: {min(results.values()) if results else 0.0} GB/s")
    print("Please perform health checks if there are any bad nodes.")

def main():
    # Argument parsing setup
    parser = argparse.ArgumentParser(description="Find bad nodes in the cluster.")
    parser.add_argument('--parallel', action='store_true', help='Run the node check in parallel')
    parser.add_argument('hosts', nargs='*', help='Provide a host file or two host names')

    # Parse arguments
    args = parser.parse_args()

    # Call the appropriate function based on --parallel flag
    if args.parallel:
        find_bad_nodes_parallel(args.hosts)
    else:
        find_bad_nodes_serial(args.hosts)

if __name__ == "__main__":
    main()