#!/bin/bash
#
# Test script for Slurm exporters
# Generates Slurm accounting, job, user, reservation, and exporter metric data.
#
# Usage: ./test_slurm_exporters.sh [OPTIONS]
#
set -e

# Configuration
CLUSTER=${CLUSTER:-$(sacctmgr -n show cluster | awk '{print $1}' | head -1)}
REST_EXPORTER_URL=${REST_EXPORTER_URL:-http://localhost:9901}  # slurm_rest_exporter.py
JOB_EXPORTER_URL=${JOB_EXPORTER_URL:-http://localhost:9902}    # slurm_job_exporter.py
TEST_PARTITION=${TEST_PARTITION:-compute}
TEST_USER=${TEST_USER:-$USER}
JOB_SCRIPT_DIR="/tmp/slurm_test_jobs"
RESERVATION_NAME=${RESERVATION_NAME:-test_resv}

# Users to use for job submission (space-separated, must exist on all nodes)
# Default: current user. Set TEST_USERS="ubuntu alice bob" for multiple users.
TEST_USERS=${TEST_USERS:-$TEST_USER}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; }
section() { echo -e "\n${BLUE}=== $1 ===${NC}"; }

# =============================================================================
# Account Setup - Hierarchical structure for 3-node CPU cluster
# =============================================================================
setup_accounts() {
    section "Setting up hierarchical Slurm accounts"

    # Create root account if needed
    log "Creating root account..."
    sudo sacctmgr -i add account root description="Root Account" organization="Test" 2>/dev/null || true

    # Level 1: Top-level teams
    log "Creating Level 1 accounts (teams)..."
    for team in ai engineering research; do
        sudo sacctmgr -i add account $team parent=root description="$team team" 2>/dev/null || true
    done

    # Level 2: Sub-teams
    log "Creating Level 2 accounts (sub-teams)..."
    sudo sacctmgr -i add account ml parent=ai description="Machine Learning" 2>/dev/null || true
    sudo sacctmgr -i add account infra parent=ai description="Infrastructure" 2>/dev/null || true
    sudo sacctmgr -i add account hpc parent=engineering description="HPC Team" 2>/dev/null || true
    sudo sacctmgr -i add account devops parent=engineering description="DevOps Team" 2>/dev/null || true
    sudo sacctmgr -i add account data parent=research description="Data Science" 2>/dev/null || true
    sudo sacctmgr -i add account analytics parent=research description="Analytics" 2>/dev/null || true

    # Level 3: Projects
    log "Creating Level 3 accounts (projects)..."
    sudo sacctmgr -i add account training parent=ml description="ML Training" 2>/dev/null || true
    sudo sacctmgr -i add account inference parent=ml description="ML Inference" 2>/dev/null || true
    sudo sacctmgr -i add account benchmark parent=hpc description="Benchmarking" 2>/dev/null || true
    sudo sacctmgr -i add account simulation parent=hpc description="Simulations" 2>/dev/null || true

    log "Accounts created successfully"
    echo ""
    sacctmgr show account format=Account%20,ParentName%15,Description%30
}

# =============================================================================
# User Setup - Add existing users to Slurm accounts
# =============================================================================
setup_users() {
    section "Setting up user associations"

    # All accounts to add users to
    local all_accounts=("training" "inference" "ml" "benchmark" "simulation" "hpc" "data" "analytics" "ai" "engineering" "research")

    # Add each user in TEST_USERS to all accounts
    for user in $TEST_USERS; do
        # Verify user exists on system
        if ! id "$user" &>/dev/null; then
            warn "User $user does not exist on this system - skipping"
            continue
        fi

        log "Adding user $user to all test accounts..."
        for account in "${all_accounts[@]}"; do
            sudo sacctmgr -i add user "$user" account="$account" 2>/dev/null || true
        done
    done

    log "User associations configured"
    echo ""
    sacctmgr show user withassoc format=User%15,Account%20,DefaultAccount%15
}

# =============================================================================
# Job Scripts - Create test job scripts for CPU workloads
# =============================================================================
create_job_scripts() {
    section "Creating test job scripts"

    mkdir -p "$JOB_SCRIPT_DIR"

    # Create log directory
    mkdir -p /tmp/slurm_logs 2>/dev/null || true

    # Short CPU job (1-2 minutes)
    cat > "$JOB_SCRIPT_DIR/short_cpu.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=short_cpu
#SBATCH --time=00:05:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=512M
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Short CPU job started on $(hostname) at $(date)"
echo "Using $SLURM_CPUS_PER_TASK CPUs"

# Light CPU work for ~1-2 minutes
for i in {1..60}; do
    awk 'BEGIN{for(i=0;i<50000;i++)x+=sin(i)}' &
done
wait

echo "Job completed at $(date)"
EOF

    # Medium CPU job (5-10 minutes)
    cat > "$JOB_SCRIPT_DIR/medium_cpu.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=medium_cpu
#SBATCH --time=00:15:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=1G
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Medium CPU job started on $(hostname) at $(date)"

# CPU stress for ~5 minutes
end_time=$((SECONDS + 300))
while [ $SECONDS -lt $end_time ]; do
    for i in $(seq 1 $SLURM_CPUS_PER_TASK); do
        awk 'BEGIN{for(i=0;i<100000;i++)x+=sin(i)*cos(i)}' &
    done
    wait
done

echo "Job completed at $(date)"
EOF

    # Long CPU job (15-30 minutes)
    cat > "$JOB_SCRIPT_DIR/long_cpu.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=long_cpu
#SBATCH --time=00:45:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=2G
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Long CPU job started on $(hostname) at $(date)"

# Run for ~20 minutes
for round in {1..20}; do
    echo "Round $round/20 at $(date)"
    for i in $(seq 1 $SLURM_CPUS_PER_TASK); do
        awk 'BEGIN{for(i=0;i<200000;i++)x+=sin(i)*cos(i)}' &
    done
    wait
    sleep 30
done

echo "Job completed at $(date)"
EOF

    # Multi-node job (uses 2+ nodes)
    cat > "$JOB_SCRIPT_DIR/multinode.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=multinode
#SBATCH --time=00:10:00
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=2
#SBATCH --cpus-per-task=2
#SBATCH --mem-per-cpu=256M
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Multi-node job started at $(date)"
echo "Nodes: $SLURM_JOB_NODELIST"
echo "Tasks: $SLURM_NTASKS"

srun hostname
srun bash -c 'for i in {1..100}; do awk "BEGIN{for(j=0;j<50000;j++)x+=sin(j)}"; done'

echo "Job completed at $(date)"
EOF

    # Array job
    cat > "$JOB_SCRIPT_DIR/array_job.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=array_test
#SBATCH --time=00:05:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=256M
#SBATCH --array=1-5
#SBATCH --output=/tmp/slurm_logs/%x_%A_%a.out
#SBATCH --error=/tmp/slurm_logs/%x_%A_%a.err

echo "Array task $SLURM_ARRAY_TASK_ID of $SLURM_ARRAY_TASK_COUNT started"
sleep $((20 + SLURM_ARRAY_TASK_ID * 10))
awk "BEGIN{for(i=0;i<$((SLURM_ARRAY_TASK_ID * 50000));i++)x+=sin(i)}"
echo "Task $SLURM_ARRAY_TASK_ID completed"
EOF

    # Job that will fail
    cat > "$JOB_SCRIPT_DIR/fail_job.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=fail_test
#SBATCH --time=00:02:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=128M
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "This job will fail intentionally"
sleep 10
exit 1
EOF

    # Memory-intensive job
    cat > "$JOB_SCRIPT_DIR/memory_job.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=memory_test
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=2G
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Memory-intensive job started"

# Allocate and use memory
python3 -c "
import time
data = []
for i in range(50):
    data.append([x*x for x in range(100000)])
    print(f'Allocated block {i+1}/50')
    time.sleep(5)
print('Memory test completed')
" 2>/dev/null || {
    # Fallback if python not available
    dd if=/dev/zero of=/tmp/memtest_$SLURM_JOB_ID bs=1M count=500
    sleep 120
    rm -f /tmp/memtest_$SLURM_JOB_ID
}

echo "Job completed"
EOF

    # Quick job for rapid testing
    cat > "$JOB_SCRIPT_DIR/quick_job.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=quick
#SBATCH --time=00:01:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=128M
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Quick job on $(hostname)"
sleep 15
echo "Done"
EOF

    # ===========================================
    # GPU Jobs - A100 workloads
    # ===========================================

    # Single GPU training job (uses 1 GPU, ~10 min)
    cat > "$JOB_SCRIPT_DIR/gpu_single.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=gpu_single
#SBATCH --time=00:15:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Single GPU job started on $(hostname) at $(date)"
echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"
nvidia-smi

# GPU stress using PyTorch matrix operations
python3 << 'PYTHON'
import torch
import time

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"Using device: {device}")

# Matrix multiplication stress test
size = 8192
duration = 600  # 10 minutes
start = time.time()

while time.time() - start < duration:
    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)
    c = torch.mm(a, b)
    torch.cuda.synchronize()
    if int(time.time() - start) % 60 == 0:
        print(f"Running for {int(time.time() - start)}s...")

print("GPU stress test completed")
PYTHON

echo "Job completed at $(date)"
EOF

    # Multi-GPU training job (uses 4 GPUs, ~15 min)
    cat > "$JOB_SCRIPT_DIR/gpu_multi.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=gpu_multi
#SBATCH --time=00:20:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=128G
#SBATCH --gres=gpu:4
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Multi-GPU job started on $(hostname) at $(date)"
echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"
nvidia-smi

# Multi-GPU stress
python3 << 'PYTHON'
import torch
import torch.multiprocessing as mp
import time
import os

def gpu_worker(gpu_id, duration):
    torch.cuda.set_device(gpu_id)
    device = torch.device(f'cuda:{gpu_id}')
    print(f"Worker started on GPU {gpu_id}")

    size = 8192
    start = time.time()
    ops = 0

    while time.time() - start < duration:
        a = torch.randn(size, size, device=device)
        b = torch.randn(size, size, device=device)
        c = torch.mm(a, b)
        torch.cuda.synchronize()
        ops += 1

    print(f"GPU {gpu_id}: completed {ops} operations")

if __name__ == '__main__':
    num_gpus = torch.cuda.device_count()
    print(f"Found {num_gpus} GPUs")

    duration = 900  # 15 minutes
    processes = []

    for gpu_id in range(num_gpus):
        p = mp.Process(target=gpu_worker, args=(gpu_id, duration))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

    print("All GPU workers completed")
PYTHON

echo "Job completed at $(date)"
EOF

    # Full node GPU job (all 8 GPUs, ~20 min)
    cat > "$JOB_SCRIPT_DIR/gpu_fullnode.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=gpu_fullnode
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=256G
#SBATCH --gres=gpu:8
#SBATCH --exclusive
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Full node GPU job started on $(hostname) at $(date)"
nvidia-smi

python3 << 'PYTHON'
import torch
import torch.multiprocessing as mp
import time

def gpu_stress(gpu_id, duration):
    torch.cuda.set_device(gpu_id)
    device = torch.device(f'cuda:{gpu_id}')

    # Larger matrices for full utilization
    size = 10240
    start = time.time()

    while time.time() - start < duration:
        a = torch.randn(size, size, device=device)
        b = torch.randn(size, size, device=device)
        c = torch.mm(a, b)
        # Also do some memory operations
        d = c.clone()
        e = torch.sigmoid(d)
        torch.cuda.synchronize()

if __name__ == '__main__':
    num_gpus = torch.cuda.device_count()
    duration = 1200  # 20 minutes

    processes = []
    for gpu_id in range(num_gpus):
        p = mp.Process(target=gpu_stress, args=(gpu_id, duration))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()
PYTHON

echo "Job completed at $(date)"
EOF

    # Multi-node GPU job (2 nodes, all GPUs)
    cat > "$JOB_SCRIPT_DIR/gpu_multinode.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=gpu_multinode
#SBATCH --time=00:30:00
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=8
#SBATCH --cpus-per-task=8
#SBATCH --mem=256G
#SBATCH --gres=gpu:8
#SBATCH --exclusive
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Multi-node GPU job started at $(date)"
echo "Nodes: $SLURM_JOB_NODELIST"
echo "Tasks: $SLURM_NTASKS"

srun bash -c '
echo "Task $SLURM_PROCID on $(hostname) GPU $CUDA_VISIBLE_DEVICES"
nvidia-smi -L

python3 << PYTHON
import torch
import time

gpu_id = int("$SLURM_LOCALID")
torch.cuda.set_device(gpu_id)
device = torch.device(f"cuda:{gpu_id}")

size = 8192
duration = 1200  # 20 minutes
start = time.time()

while time.time() - start < duration:
    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)
    c = torch.mm(a, b)
    torch.cuda.synchronize()

print(f"GPU {gpu_id} on $(hostname) completed")
PYTHON
'

echo "Job completed at $(date)"
EOF

    # GPU memory stress job
    cat > "$JOB_SCRIPT_DIR/gpu_memory.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=gpu_memory
#SBATCH --time=00:15:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:2
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "GPU memory stress job on $(hostname)"
nvidia-smi

python3 << 'PYTHON'
import torch
import time

# Allocate large tensors to use GPU memory
tensors = []
for gpu_id in range(torch.cuda.device_count()):
    device = torch.device(f'cuda:{gpu_id}')
    # Allocate ~30GB per GPU (A100 40GB)
    for i in range(6):
        t = torch.randn(1024, 1024, 1280, device=device)  # ~5GB each
        tensors.append(t)
    print(f"GPU {gpu_id}: allocated ~30GB")

# Keep memory allocated and do some work
for i in range(600):  # 10 minutes
    for t in tensors:
        _ = t * 2.0
    if i % 60 == 0:
        print(f"Running for {i}s...")
    time.sleep(1)
PYTHON

echo "Job completed at $(date)"
EOF

    # Quick GPU test job
    cat > "$JOB_SCRIPT_DIR/gpu_quick.sh" << 'EOF'
#!/bin/bash
#SBATCH --job-name=gpu_quick
#SBATCH --time=00:05:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --gres=gpu:1
#SBATCH --output=/tmp/slurm_logs/%x_%j.out
#SBATCH --error=/tmp/slurm_logs/%x_%j.err

echo "Quick GPU test on $(hostname)"
nvidia-smi

python3 << 'PYTHON'
import torch
import time

device = torch.device('cuda')
size = 4096

for i in range(120):  # 2 minutes
    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)
    c = torch.mm(a, b)
    torch.cuda.synchronize()
    time.sleep(1)

print("Quick GPU test done")
PYTHON
EOF

    chmod +x "$JOB_SCRIPT_DIR"/*.sh
    log "Job scripts created in $JOB_SCRIPT_DIR"
    ls -la "$JOB_SCRIPT_DIR"
}

# =============================================================================
# Helper: Submit job as specific user
# =============================================================================
submit_as_user() {
    local user=$1
    local account=$2
    local script=$3
    local extra_args=${4:-}

    # Use sudo to submit as the specified user if different from current
    if [ "$user" != "$USER" ]; then
        if sudo -n true 2>/dev/null; then
            sudo -u "$user" sbatch --account="$account" --partition="$TEST_PARTITION" $extra_args "$script" 2>/dev/null
        else
            warn "Cannot sudo to $user, submitting as $USER"
            sbatch --account="$account" --partition="$TEST_PARTITION" $extra_args "$script" 2>/dev/null
        fi
    else
        sbatch --account="$account" --partition="$TEST_PARTITION" $extra_args "$script" 2>/dev/null
    fi
}

# =============================================================================
# Helper: Get user from TEST_USERS list (cycles through)
# =============================================================================
get_test_user() {
    local index=$1
    local users_array=($TEST_USERS)
    local count=${#users_array[@]}
    echo "${users_array[$((index % count))]}"
}

# =============================================================================
# Helper: Detect GPU resources
# =============================================================================
has_gpu_resources() {
    sinfo -h -o "%G" 2>/dev/null | grep -Eqi '(^|,|:)gpu|gres/gpu'
}

# =============================================================================
# Submit Jobs - Generate workload data with GPU jobs
# =============================================================================
submit_jobs() {
    section "Submitting test jobs (CPU + GPU)"

    create_job_scripts

    # Auto-detect partition if not set
    if ! sinfo -p "$TEST_PARTITION" &>/dev/null; then
        TEST_PARTITION=$(sinfo -h -o "%P" | head -1 | tr -d '*')
        log "Using partition: $TEST_PARTITION"
    fi

    log "Using users: $TEST_USERS"

    local submitted=0
    local user_idx=0

    # Define accounts to use
    local gpu_accounts=("training" "ml" "benchmark" "simulation" "data")
    local cpu_accounts=("training" "inference" "benchmark" "hpc" "data" "analytics")

    # =====================================================
    # GPU Jobs - Cycle through users and accounts
    # =====================================================
    if has_gpu_resources; then
        log "Submitting GPU jobs..."

        for account in "${gpu_accounts[@]}"; do
            local user=$(get_test_user $user_idx)
            log "$user: GPU jobs (account=$account)"

            submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/gpu_single.sh" && ((submitted++)) || true
            submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/gpu_multi.sh" && ((submitted++)) || true
            submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/gpu_quick.sh" && ((submitted++)) || true

            ((user_idx++))
        done

        # Full node and multi-node jobs
        user=$(get_test_user 0)
        log "$user: Full node GPU job (account=training)"
        submit_as_user "$user" "training" "$JOB_SCRIPT_DIR/gpu_fullnode.sh" && ((submitted++)) || true

        user=$(get_test_user 1)
        log "$user: Multi-node GPU job (account=benchmark)"
        submit_as_user "$user" "benchmark" "$JOB_SCRIPT_DIR/gpu_multinode.sh" && ((submitted++)) || true
    else
        warn "No GPU resources detected by sinfo; skipping GPU job submissions"
    fi

    # =====================================================
    # CPU Jobs - Cycle through users and accounts
    # =====================================================
    log "Submitting CPU jobs..."

    user_idx=0
    for account in "${cpu_accounts[@]}"; do
        local user=$(get_test_user $user_idx)
        log "$user: CPU jobs (account=$account)"

        submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/short_cpu.sh" && ((submitted++)) || true
        submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/medium_cpu.sh" && ((submitted++)) || true

        ((user_idx++))
    done

    # Multi-node CPU job
    user=$(get_test_user 0)
    submit_as_user "$user" "hpc" "$JOB_SCRIPT_DIR/multinode.sh" && ((submitted++)) || true

    # Array job
    user=$(get_test_user 1)
    submit_as_user "$user" "training" "$JOB_SCRIPT_DIR/array_job.sh" && ((submitted++)) || true

    # =====================================================
    # Failing jobs for metrics variety
    # =====================================================
    log "Submitting jobs that will fail (for error metrics)..."
    user=$(get_test_user 0)
    submit_as_user "$user" "training" "$JOB_SCRIPT_DIR/fail_job.sh" && ((submitted++)) || true
    submit_as_user "$user" "benchmark" "$JOB_SCRIPT_DIR/fail_job.sh" && ((submitted++)) || true

    log "Submitted $submitted jobs"
    echo ""
    echo "=== Job Queue ==="
    squeue -o "%.8i %.12j %.10u %.12a %.8T %.10M %.6D %.4C %R" | head -30
}

# =============================================================================
# Submit CPU-only Jobs
# =============================================================================
submit_cpu_jobs() {
    section "Submitting CPU-only test jobs"

    create_job_scripts

    # Auto-detect partition if not set
    if ! sinfo -p "$TEST_PARTITION" &>/dev/null; then
        TEST_PARTITION=$(sinfo -h -o "%P" | head -1 | tr -d '*')
        log "Using partition: $TEST_PARTITION"
    fi

    log "Using users: $TEST_USERS"

    local submitted=0
    local user_idx=0
    local cpu_accounts=("training" "inference" "benchmark" "hpc" "data" "analytics")

    for account in "${cpu_accounts[@]}"; do
        local user=$(get_test_user $user_idx)
        log "$user: CPU jobs (account=$account)"

        submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/short_cpu.sh" && ((submitted++)) || true
        submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/medium_cpu.sh" && ((submitted++)) || true

        ((user_idx++))
    done

    local user
    user=$(get_test_user 0)
    submit_as_user "$user" "hpc" "$JOB_SCRIPT_DIR/long_cpu.sh" && ((submitted++)) || true
    submit_as_user "$user" "hpc" "$JOB_SCRIPT_DIR/multinode.sh" && ((submitted++)) || true

    user=$(get_test_user 1)
    submit_as_user "$user" "data" "$JOB_SCRIPT_DIR/memory_job.sh" && ((submitted++)) || true
    submit_as_user "$user" "training" "$JOB_SCRIPT_DIR/array_job.sh" && ((submitted++)) || true

    log "Submitting CPU jobs that will fail intentionally (for error metrics)..."
    user=$(get_test_user 0)
    submit_as_user "$user" "training" "$JOB_SCRIPT_DIR/fail_job.sh" && ((submitted++)) || true
    submit_as_user "$user" "benchmark" "$JOB_SCRIPT_DIR/fail_job.sh" && ((submitted++)) || true

    log "Submitted $submitted CPU-only jobs"
    echo ""
    echo "=== Job Queue ==="
    squeue -o "%.8i %.12j %.10u %.12a %.8T %.10M %.6D %.4C %R" | head -30
}

# =============================================================================
# Submit GPU-only Jobs - Heavy GPU workload
# =============================================================================
submit_gpu_jobs() {
    section "Submitting GPU-intensive jobs only"

    create_job_scripts

    if ! has_gpu_resources; then
        warn "No GPU resources detected by sinfo; nothing to submit"
        return 1
    fi

    log "Using users: $TEST_USERS"

    local submitted=0
    local accounts=("training" "ml" "benchmark" "simulation" "data")

    log "Submitting heavy GPU workloads to maximize utilization..."

    # Full node jobs
    local user=$(get_test_user 0)
    submit_as_user "$user" "training" "$JOB_SCRIPT_DIR/gpu_fullnode.sh" && ((submitted++)) || warn "Failed"

    user=$(get_test_user 1)
    submit_as_user "$user" "benchmark" "$JOB_SCRIPT_DIR/gpu_fullnode.sh" && ((submitted++)) || warn "Failed"

    # Multi-node job spanning both nodes
    user=$(get_test_user 0)
    submit_as_user "$user" "ml" "$JOB_SCRIPT_DIR/gpu_multinode.sh" && ((submitted++)) || warn "Failed"

    # Queue up more GPU jobs cycling through users and accounts
    local user_idx=0
    for account in "${accounts[@]}"; do
        user=$(get_test_user $user_idx)
        submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/gpu_multi.sh" && ((submitted++)) || true
        submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/gpu_single.sh" && ((submitted++)) || true
        submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/gpu_memory.sh" && ((submitted++)) || true
        ((user_idx++))
    done

    log "Submitted $submitted GPU jobs"
    squeue -o "%.8i %.12j %.10u %.12a %.8T %.10M %.6D %.4C %.8b %R"
}

# =============================================================================
# Generate Historical Data - Create past job records
# =============================================================================
generate_history() {
    section "Generating historical job data"

    create_job_scripts

    log "Using users: $TEST_USERS"
    log "Submitting batch of jobs for historical data..."

    local accounts=("training" "inference" "ml" "benchmark" "simulation" "hpc" "data" "analytics")
    local user_idx=0

    for account in "${accounts[@]}"; do
        local user=$(get_test_user $user_idx)
        log "Submitting 5 jobs: user=$user account=$account"

        for i in {1..5}; do
            submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/quick_job.sh"
            if has_gpu_resources; then
                submit_as_user "$user" "$account" "$JOB_SCRIPT_DIR/gpu_quick.sh"
            fi
        done

        ((user_idx++))
    done

    log "Historical data jobs submitted. Wait for completion to see in sacct."
    squeue -o "%.8i %.12j %.10u %.12a %.8T %.6D %R" | head -40
}

# =============================================================================
# Create Reservation
# =============================================================================
create_reservation() {
    section "Creating test reservation"

    local node
    node=$(sinfo -N -h -o "%N" | head -1)

    if [ -z "$node" ]; then
        warn "No nodes available for reservation"
        return 0
    fi

    local users
    users=$(echo "$TEST_USERS" | sed 's/[[:space:]][[:space:]]*/,/g')

    local start
    start=$(date +%Y-%m-%dT%H:%M:%S)

    scontrol create reservation="$RESERVATION_NAME" \
        starttime="$start" duration=60 \
        nodes="$node" users="$users" \
        flags=maint 2>/dev/null && \
        log "Created reservation '$RESERVATION_NAME' on node $node for users $users" || \
        warn "Failed to create reservation '$RESERVATION_NAME' (may need Slurm admin privileges)"
}

# =============================================================================
# Check Metrics
# =============================================================================
check_metrics() {
    section "Checking exporter metrics"

    echo ""
    echo "=== REST Exporter ($REST_EXPORTER_URL) ==="
    if curl -s --connect-timeout 5 "$REST_EXPORTER_URL/metrics" > /tmp/rest_metrics.txt 2>/dev/null; then
        log "REST exporter is responding"

        echo ""
        echo "Node metrics:"
        grep -E "^slurm_node_state_count|^slurm_cpus_total|^slurm_gpus_total|^slurm_nodes_total" /tmp/rest_metrics.txt 2>/dev/null | head -10

        echo ""
        echo "Job metrics:"
        grep -E "^slurm_jobs_running|^slurm_jobs_pending|^slurm_job_info" /tmp/rest_metrics.txt 2>/dev/null | head -10

        echo ""
        echo "Partition metrics:"
        grep -E "^slurm_partition_" /tmp/rest_metrics.txt 2>/dev/null | head -10

        echo ""
        echo "Account metrics:"
        grep -E "^slurm_account_" /tmp/rest_metrics.txt 2>/dev/null | head -10

        echo ""
        echo "User metrics:"
        grep -E "^slurm_alloc_.*_user_count" /tmp/rest_metrics.txt 2>/dev/null | head -10

        echo ""
        echo "Reservation metrics:"
        grep -E "^slurm_.*reservation" /tmp/rest_metrics.txt 2>/dev/null | head -10
    else
        warn "REST exporter not responding at $REST_EXPORTER_URL"
    fi

    echo ""
    echo "=== Job Exporter ($JOB_EXPORTER_URL) ==="
    if curl -s --connect-timeout 5 "$JOB_EXPORTER_URL/metrics" > /tmp/job_metrics.txt 2>/dev/null; then
        log "Job exporter is responding"
        grep -E "^slurm_" /tmp/job_metrics.txt 2>/dev/null | head -20
    else
        warn "Job exporter not responding at $JOB_EXPORTER_URL"
    fi
}

# =============================================================================
# Verify Metrics
# =============================================================================
verify_metrics() {
    section "Verifying expected metrics"

    local METRICS_FILE="/tmp/rest_metrics.txt"
    curl -s --connect-timeout 5 "$REST_EXPORTER_URL/metrics" > "$METRICS_FILE" 2>/dev/null

    if [ ! -s "$METRICS_FILE" ]; then
        err "Could not fetch metrics from REST exporter"
        return 1
    fi

    local EXPECTED_METRICS=(
        "slurm_node_state_count"
        "slurm_cpus_total"
        "slurm_nodes_total"
        "slurm_jobs_running"
        "slurm_jobs_pending"
        "slurm_partition_jobs_cpus_total"
        "slurm_partition_idle_cpus_total"
        "slurm_alloc_cpus_user_count"
        "slurm_collection_seconds"
    )

    local OPTIONAL_METRICS=(
        "slurm_effective_cpus_total"
        "slurm_gpus_total"
        "slurm_job_info"
        "slurm_partition_jobs_nodes_total"
        "slurm_partition_jobs_gpus_total"
        "slurm_partition_idle_nodes_total"
        "slurm_partition_node_state_count"
        "slurm_alloc_gpus_user_count"
        "slurm_alloc_nodes_user_count"
        "slurm_active_reservations_nodes_total"
        "slurm_active_reservations_cpus_total"
        "slurm_reservation_idle_cpus_total"
        "slurm_account_jobs"
        "slurm_account_gpus"
    )

    local PASS=0
    local FAIL=0

    for metric in "${EXPECTED_METRICS[@]}"; do
        if grep -q "^${metric}" "$METRICS_FILE"; then
            echo -e "${GREEN}✓${NC} $metric"
            ((PASS++))
        else
            echo -e "${RED}✗${NC} $metric (missing)"
            ((FAIL++))
        fi
    done

    echo ""
    log "Core results: $PASS passed, $FAIL missing"

    echo ""
    echo "Optional metrics:"
    for metric in "${OPTIONAL_METRICS[@]}"; do
        if grep -q "^${metric}" "$METRICS_FILE"; then
            echo -e "${GREEN}✓${NC} $metric"
        else
            echo -e "${YELLOW}-${NC} $metric (not present)"
        fi
    done

    if [ $FAIL -eq 0 ]; then
        log "All core metrics verified!"
    else
        warn "Some metrics missing. Ensure slurmrestd is running and jobs are active."
    fi
}

# =============================================================================
# Show Slurm Status
# =============================================================================
show_status() {
    section "Slurm Cluster Status"

    echo ""
    echo "=== Nodes ==="
    sinfo -N -l 2>/dev/null || sinfo

    echo ""
    echo "=== Partitions ==="
    sinfo -s

    echo ""
    echo "=== Queue ==="
    squeue

    echo ""
    echo "=== Recent Jobs (sacct) ==="
    sacct -S "$(date -d '1 hour ago' '+%Y-%m-%dT%H:%M:%S' 2>/dev/null || date -v-1H '+%Y-%m-%dT%H:%M:%S')" \
          --format=JobID,JobName,User,Account,State,ExitCode,Elapsed,NCPUs,NNodes 2>/dev/null | head -20

    echo ""
    echo "=== Accounts ==="
    sacctmgr show account format=Account%20,ParentName%15 2>/dev/null | head -20
}

# =============================================================================
# Cleanup
# =============================================================================
cleanup() {
    section "Cleaning up test data"

    log "Cancelling jobs from users: $TEST_USERS"
    for user in $TEST_USERS; do
        scancel -u "$user" 2>/dev/null || true
    done

    log "Deleting reservation $RESERVATION_NAME if present..."
    scontrol delete reservation="$RESERVATION_NAME" 2>/dev/null || true

    log "Removing job scripts..."
    rm -rf "$JOB_SCRIPT_DIR"

    log "Cleanup complete"
}

# =============================================================================
# Undo Setup - Remove test accounts from Slurm (keeps users)
# =============================================================================
undo_setup() {
    section "Removing test accounts from Slurm"

    # Cancel any running jobs from test users first
    log "Cancelling jobs from users: $TEST_USERS"
    for user in $TEST_USERS; do
        scancel -u "$user" 2>/dev/null || true
    done

    log "Deleting reservation $RESERVATION_NAME if present..."
    scontrol delete reservation="$RESERVATION_NAME" 2>/dev/null || true

    # Remove user associations from test accounts
    log "Removing user associations from test accounts..."
    local all_accounts=("training" "inference" "ml" "benchmark" "simulation" "hpc" "data" "analytics" "ai" "engineering" "research")
    for user in $TEST_USERS; do
        for account in "${all_accounts[@]}"; do
            sudo sacctmgr -i delete user name="$user" account="$account" 2>/dev/null || true
        done
    done

    # Remove Level 3 accounts (projects) - must remove children before parents
    log "Removing Level 3 accounts (projects)..."
    for acct in training inference benchmark simulation; do
        sudo sacctmgr -i delete account name="$acct" 2>/dev/null || true
    done

    # Remove Level 2 accounts (sub-teams)
    log "Removing Level 2 accounts (sub-teams)..."
    for acct in ml infra hpc devops data analytics; do
        sudo sacctmgr -i delete account name="$acct" 2>/dev/null || true
    done

    # Remove Level 1 accounts (teams)
    log "Removing Level 1 accounts (teams)..."
    for acct in ai engineering research; do
        sudo sacctmgr -i delete account name="$acct" 2>/dev/null || true
    done

    log "Slurm test accounts removed"
    echo ""
    echo "=== Remaining Accounts ==="
    sacctmgr show account format=Account%20,ParentName%15 2>/dev/null

    echo ""
    echo "=== Remaining Users ==="
    sacctmgr show user format=User%15,Account%20 2>/dev/null
}

# =============================================================================
# Full Test Cycle
# =============================================================================
run_full_test() {
    section "Running full test cycle"

    setup_accounts
    setup_users
    submit_jobs
    create_reservation

    log "Waiting 30 seconds for jobs to start..."
    sleep 30

    check_metrics
    verify_metrics
    show_status
}

# =============================================================================
# Usage
# =============================================================================
usage() {
    cat << EOF
Slurm Exporter Test Script

Usage: $0 [OPTIONS]

Options:
    --setup-accounts    Create hierarchical Slurm accounts
    --setup-users       Create test users and account associations
    --create-scripts    Create job submission scripts (CPU + GPU)
    --submit-jobs       Submit test jobs (CPU + GPU) as different users
    --submit-cpu-jobs   Submit CPU-only jobs
    --submit-gpu-jobs   Submit GPU-intensive jobs only (maximize utilization)
    --generate-history  Submit many jobs to build historical data
    --create-reservation Create test reservation (requires Slurm admin)
    --check-metrics     Check exporter metrics endpoints
    --verify-metrics    Verify expected metrics are present
    --show-status       Show current Slurm cluster status
    --cleanup           Cancel jobs and cleanup test files
    --undo-setup        Remove test accounts from Slurm
    --full-test         Run complete test cycle
    --all               Alias for --full-test
    --help, -h          Show this help message

Environment Variables:
    CLUSTER             Slurm cluster name (auto-detected)
    REST_EXPORTER_URL   REST exporter URL (default: http://localhost:9901)
    JOB_EXPORTER_URL    Job exporter URL (default: http://localhost:9902)
    TEST_PARTITION      Partition for test jobs (default: compute)
    TEST_USER           Primary test user (default: current user)
    TEST_USERS          Space-separated users for jobs (default: TEST_USER)
                        Example: TEST_USERS="ubuntu alice bob"
    RESERVATION_NAME    Test reservation name (default: test_resv)

Examples:
    # Setup accounts and add ubuntu user to all accounts
    sudo $0 --setup-accounts --setup-users

    # Submit jobs as the current user by default
    $0 --submit-jobs

    # Submit CPU-only jobs
    $0 --submit-cpu-jobs

    # Submit GPU-heavy workload only
    $0 --submit-gpu-jobs

    # Use multiple users (must exist on all nodes)
    TEST_USERS="ubuntu alice bob" $0 --setup-users --submit-jobs

    # Generate historical data
    $0 --generate-history

    # Check exporters
    $0 --check-metrics --verify-metrics

    # Cleanup test accounts
    sudo $0 --undo-setup

Account Hierarchy Created:
    root
    |-- ai
    |   |-- ml
    |   |   |-- training
    |   |   \`-- inference
    |   \`-- infra
    |-- engineering
    |   |-- hpc
    |   |   |-- benchmark
    |   |   \`-- simulation
    |   \`-- devops
    \`-- research
        |-- data
        \`-- analytics
EOF
}

# =============================================================================
# Main
# =============================================================================
if [ $# -eq 0 ]; then
    usage
    exit 0
fi

while [ $# -gt 0 ]; do
    case "$1" in
        --setup-accounts)
            setup_accounts
            ;;
        --setup-users)
            setup_users
            ;;
        --create-scripts)
            create_job_scripts
            ;;
        --submit-jobs)
            submit_jobs
            ;;
        --submit-cpu-jobs)
            submit_cpu_jobs
            ;;
        --submit-gpu-jobs)
            submit_gpu_jobs
            ;;
        --generate-history)
            generate_history
            ;;
        --create-reservation)
            create_reservation
            ;;
        --check-metrics)
            check_metrics
            ;;
        --verify-metrics)
            verify_metrics
            ;;
        --show-status)
            show_status
            ;;
        --cleanup)
            cleanup
            ;;
        --undo-setup)
            undo_setup
            ;;
        --full-test)
            run_full_test
            ;;
        --all)
            run_full_test
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            err "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
    shift
done
