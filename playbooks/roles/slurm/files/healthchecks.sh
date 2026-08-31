#!/bin/sh

# Fetch the instance shape
shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)
NODE=$(hostname)
# Check if the shape matches the desired GPU types
if [ ${shape} = "BM.GPU.H100.8" ] || \
   [ ${shape} = "BM.GPU.A100-v2.8" ] || \
   [ ${shape} = "BM.GPU4.8" ] || \
   [ ${shape} = "BM.GPU.B4.8" ] || \
   [ ${shape} = "BM.GPU.H200.8" ] || \
   [ ${shape} = "BM.GPU.MI300X.8" ] || \
   [ ${shape} = "BM.GPU.MI355X-v0.8" ] || \
   [ ${shape} = "BM.GPU.MI355X-v1.8" ] || \
   [ ${shape} = "BM.GPU.GB200.4" ] || \
   [ ${shape} = "BM.GPU.GB200-v2.4" ] || \
   [ ${shape} = "BM.GPU.GB200-v3.4" ] || \
   [ ${shape} = "BM.GPU.GB300.4" ] || \
   [ ${shape} = "BM.GPU.B200.8" ] || \
   [ ${shape} = "BM.GPU.B300.8" ] || \
   [ ${shape} = "BM.GPU.B300.HS.8" ] || \
   [ ${shape} = "BM.GPU.RTXPRO.8" ]; then

  FILE="/var/log/healthchecks/latest_healthcheck.log"
  if [ -e "$FILE" ]; then
    # Get the current time and the file's last modification time
    CURRENT_TIME=$(date +%s)
    FILE_MOD_TIME=$(stat -c %Y "$FILE")

    # Calculate the time difference in seconds
    TIME_DIFF=$((CURRENT_TIME - FILE_MOD_TIME))
  else
    TIME_DIFF=600
  fi

  # Check if the file is older than 60 seconds (1 minute)
  if [ $TIME_DIFF -gt 60 ]; then
    sudo /config/bin/uv_wrapper.sh run-venv /opt/oci-hpc/healthchecks/check_gpu_setup.py --slurm 2>&1
  fi

  # Check for healthcheck messages
  DRAIN_MSG=$(grep "Healthcheck::" /var/log/healthchecks/latest_healthcheck.log)
  if [ -n "$DRAIN_MSG" ]; then
    JIRA_TICKET_FILE="/etc/slurm/prolog.d/healthcheck_jira_tickets.tsv"
    JIRA_KEY=""
    if [ -r "$JIRA_TICKET_FILE" ]; then
      JIRA_KEY=$(awk -v node="$NODE" '$1 == node {print $2; exit}' "$JIRA_TICKET_FILE")
    fi
    if [ -z "$JIRA_KEY" ]; then
      CURRENT_REASON=$(scontrol show node="$NODE" | awk -F= '/Reason=/{print $2}')
      JIRA_KEY=$(printf '%s\n' "$CURRENT_REASON" | sed -n 's/^Healthcheck:: \([A-Z][A-Z0-9]*-[0-9][0-9]*\) .*/\1/p' | head -n 1)
    fi
    if [ -n "$JIRA_KEY" ] && ! printf '%s\n' "$DRAIN_MSG" | grep -E '^Healthcheck:: [A-Z][A-Z0-9]*-[0-9][0-9]* ' >/dev/null 2>&1; then
      DRAIN_MSG=$(printf '%s\n' "$DRAIN_MSG" | sed "s/^Healthcheck:: /Healthcheck:: ${JIRA_KEY} /")
    fi
    if [ -n "$SLURM_JOB_ID" ]; then
      echo "${DRAIN_MSG}"
      exit 1
    else
        scontrol update nodename=$NODE state=drain reason="${DRAIN_MSG}"
    fi
  else
    REASON=$(scontrol show node="$NODE" | awk -F= '/Reason=/{print $2}')
    if echo "$REASON" | grep -E '^Healthcheck::|^Prolog error' >/dev/null 2>&1; then
      scontrol update nodename=$NODE state=resume
    fi
  fi
fi
