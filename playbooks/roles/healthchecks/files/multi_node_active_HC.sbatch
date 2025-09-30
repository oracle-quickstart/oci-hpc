#!/bin/bash
#SBATCH --job-name=multi_node_active_HealthCheck
#SBATCH --nodes=2
#SBATCH --exclusive
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --output=/tmp/multi_node_active_HealthCheck/%x-%j.out  # %x = job name, %j = job ID
#SBATCH --error=/tmp/multi_node_active_HealthCheck/%x-%j.out


# Fetch the instance shape
shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)

# Check if the shape matches the desired GPU types
if [ "$shape" = "BM.GPU.H100.8" ] || \
   [ "$shape" = "BM.GPU.A100-v2.8" ] || \
   [ "$shape" = "BM.GPU4.8" ] || \
   [ "$shape" = "BM.GPU.B4.8" ] || \
   [ "$shape" = "BM.GPU.H200.8" ] || \
   [ "$shape" = "BM.GPU.B200.8" ]; then

  FILE="/tmp/latest_multi_node_active_healthcheck.log"

  if [ -f "$FILE" ]; then
    FILE_TIME=$(stat -c %Y "$FILE")
    NOW=$(date +%s)
    TIME_DIFF=$((NOW - FILE_TIME))
  else
    TIME_DIFF=9999   # Force healthcheck to run if file doesn’t exist
  fi

  scontrol show hostnames $SLURM_JOB_NODELIST > /tmp/hostfile_$SLURM_JOB_ID

  # Run healthcheck if file is older than 60s or missing
  if [ "$TIME_DIFF" -gt 60 ]; then
    # get node details
    srun --ntasks=2 --ntasks-per-node=1 timeout --preserve-status --foreground 10s python3 /opt/oci-hpc/healthchecks/multi_node_active_healthcheck.py --mode 1
    sleep 2
    # run all the multi-node active healthchecks
    python3 /opt/oci-hpc/healthchecks/multi_node_active_healthcheck.py --hostfile /tmp/hostfile_$SLURM_JOB_ID --mode 2
    sleep 2
    
    # Get the hostnames of the assigned nodes
    nodes=($(scontrol show hostname $SLURM_JOB_NODELIST))
    node1=${nodes[0]}
    node2=${nodes[1]}
    file_to_copy="/tmp/latest_multi_node_active_healthcheck.log"
    dest_path="/tmp/latest_multi_node_active_healthcheck.log"
    # Only execute the copy from the source node
    if [ "$(hostname)" == "$node1" ]; then
      # Use scp to copy the file to the second node
      scp $file_to_copy ${node2}:$dest_path
    fi
    # write to the http server file
    srun --ntasks=2 --ntasks-per-node=1 timeout --preserve-status --foreground 30s sudo python3 /opt/oci-hpc/healthchecks/multi_node_active_healthcheck.py --mode 3 --node1 $node1 --node2 $node2 --slurm
  fi
fi