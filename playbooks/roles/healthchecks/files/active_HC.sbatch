#!/bin/bash
#SBATCH --job-name=active_HealthCheck
#SBATCH --nodes=1
#SBATCH --exclusive
#SBATCH --output=/var/log/healthchecks/active_HealthCheck/%x-%j.out  # %x = job name, %j = job ID
#SBATCH --error=/var/log/healthchecks/active_HealthCheck/%x-%j.out

# Fetch the instance shape
shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)

# Check if the shape matches the desired GPU types
if [ "$shape" = "BM.GPU.H100.8" ] || \
   [ "$shape" = "BM.GPU.A100-v2.8" ] || \
   [ "$shape" = "BM.GPU4.8" ] || \
   [ "$shape" = "BM.GPU.B4.8" ] || \
   [ "$shape" = "BM.GPU.H200.8" ] || \
   [ "$shape" = "BM.GPU.GB200.4" ] || \
   [ "$shape" = "BM.GPU.GB200-v2.4" ] || \
   [ "$shape" = "BM.GPU.GB200-v3.4" ] || \
   [ "$shape" = "BM.GPU.GB300.4" ] || \
   [ "$shape" = "BM.GPU.B200.8" ] || \
   [ "$shape" = "BM.GPU.B300.8" ] || \
   [ "$shape" = "BM.GPU.MI355X.8" ] || \
   [ "$shape" = "BM.GPU.MI355X-v0.8" ] || \
   [ "$shape" = "BM.GPU.MI355X-v1.8" ] || \
   [ "$shape" = "BM.GPU.MI300X.8" ]; then

  FILE="/var/log/healthchecks/latest_active_healthcheck.log"

  if [ -f "$FILE" ]; then
    FILE_TIME=$(stat -c %Y "$FILE")
    NOW=$(date +%s)
    TIME_DIFF=$((NOW - FILE_TIME))
  else
    TIME_DIFF=9999   # Force healthcheck to run if file doesn’t exist
  fi

  source /etc/os-release
  export UV_INSTALL_DIR=/config/venv/${ID^}_${VERSION_ID}_$(uname -m)/
  export VENV_PATH=${UV_INSTALL_DIR}/oci
  # Run healthcheck if file is older than 60s or missing
  if [ "$TIME_DIFF" -gt 60 ]; then
    sudo $VENV_PATH/bin/python3 /opt/oci-hpc/healthchecks/active_healthcheck.py --slurm 2>&1
  fi

  # Only check for drain messages if log file exists
  if [ -f "$FILE" ]; then
    DRAIN_MSG=$(grep "Healthcheck_Active::" "$FILE")
    if [ -n "$DRAIN_MSG" ]; then
        sudo scontrol update nodename="$(hostname)" state=drain reason="${DRAIN_MSG}"
    fi
  fi
fi