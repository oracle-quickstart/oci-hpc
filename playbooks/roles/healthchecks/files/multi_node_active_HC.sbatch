#!/bin/bash
#SBATCH --job-name=multi_node_active_HC
#SBATCH --nodes=2
#SBATCH --exclusive
#SBATCH --gpus-per-node=8
#SBATCH --ntasks-per-node=8
#SBATCH --output=/home/ubuntu/dhvani/slurm-%j.out
#SBATCH --error=/home/ubuntu/dhvani/slurm-%j.out


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

  MACHINEFILE="hostfile"
  scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE

  # Run healthcheck if file is older than 60s or missing
  if [ "$TIME_DIFF" -gt 60 ]; then
    srun --ntasks=2 --ntasks-per-node=1 timeout --preserve-status --foreground 10s python3 /opt/oci-hpc/healthchecks/node_details.py
    sleep 2
    python3 /opt/oci-hpc/healthchecks/multi_node_active_healthcheck.py --hostfile $MACHINEFILE --slurm
    sleep 2
  fi

  # # Get the hostnames of the assigned nodes
  # nodes=($(scontrol show hostname $SLURM_JOB_NODELIST))

  # node1=${nodes[0]}
  # node2=${nodes[1]}
  # file_to_copy="/tmp/latest_multi_node_active_healthcheck.log"
  # dest_path="/tmp/latest_multi_node_active_healthcheck.log"

  # # Only execute the copy from the source node
  # if [ "$(hostname)" == "$node1" ]; then
  #   # Use scp to copy the file to the second node
  #   scp $file_to_copy ${node2}:$dest_path
  # fi

  # Extract the 'action' field
  action=$(jq -r '.action' /tmp/multi_node_hc_result.json)

  # Extract the 'reason' field
  reason=$(jq -r '.reason' /tmp/multi_node_hc_result.json)

  # Use the extracted values
  echo "Action: $action"
  echo "Reason: $reason"

  srun --ntasks=2 --ntasks-per-node=1 timeout --preserve-status --foreground 15s sudo python3 /opt/oci-hpc/healthchecks/write_hc_http_server_file.py --action $action --reason $reason --node1 $node1 --node2 $node2
  sleep 2

  # Only check for drain messages if log file exists
  if [ -f "$FILE" ]; then
    DRAIN_MSG=$(grep "Healthcheck::" "$FILE")
    if [ -n "$DRAIN_MSG" ]; then
      if [ -n "$SLURM_JOB_ID" ]; then
        echo "${DRAIN_MSG}"
        exit 1
      else
        for node in $(scontrol show hostnames $SLURM_JOB_NODELIST); do
          sudo scontrol update nodename="$(node)" state=drain reason="${DRAIN_MSG}"
        done
      fi
    fi
  fi
fi