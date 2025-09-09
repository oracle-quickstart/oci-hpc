#!/bin/bash
#SBATCH --job-name=active_HC
#SBATCH --nodes=1
#SBATCH --exclusive

# Fetch the instance shape
shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)

# Check if the shape matches the desired GPU types
if [ "$shape" = "BM.GPU.H100.8" ] || \
   [ "$shape" = "BM.GPU.A100-v2.8" ] || \
   [ "$shape" = "BM.GPU4.8" ] || \
   [ "$shape" = "BM.GPU.B4.8" ] || \
   [ "$shape" = "BM.GPU.H200.8" ] || \
   [ "$shape" = "BM.GPU.GB200.4" ] || \
   [ "$shape" = "BM.GPU.B200.8" ]; then

  FILE="/tmp/latest_active_healthcheck.log"

  if [ -f "$FILE" ]; then
    FILE_TIME=$(stat -c %Y "$FILE")
    NOW=$(date +%s)
    TIME_DIFF=$((NOW - FILE_TIME))
  else
    TIME_DIFF=9999   # Force healthcheck to run if file doesn’t exist
  fi

  # Run healthcheck if file is older than 60s or missing
  if [ "$TIME_DIFF" -gt 60 ]; then
    sudo python3 /opt/oci-hpc/healthchecks/active_healthcheck.py --slurm 2>&1
  fi

  # Only check for drain messages if log file exists
  if [ -f "$FILE" ]; then
    DRAIN_MSG=$(grep "Healthcheck::" "$FILE")
    if [ -n "$DRAIN_MSG" ]; then
      if [ -n "$SLURM_JOB_ID" ]; then
        echo "${DRAIN_MSG}"
        exit 1
      else
        sudo scontrol update nodename="$(hostname)" state=drain reason="${DRAIN_MSG}"
      fi
    fi
  fi
fi