#!/bin/bash
set -euo pipefail

MAX_CREATING=2
MAX_ACTIVE=10

LOG_ROOT="/config/logs/perjob-submit"
STATE_DIR="${LOG_ROOT}/state"
mkdir -p "${STATE_DIR}"

get_sbatch_value() {
  local key="$1"
  local file="$2"

  awk -v key="$key" '
    $1 == "#SBATCH" {
      for (i = 2; i <= NF; i++) {
        if ($i ~ "^" key "=") {
          sub("^" key "=", "", $i)
          print $i
          exit
        }
        if ($i == key && (i + 1) <= NF) {
          print $(i + 1)
          exit
        }
      }
    }
  ' "${file}"
}

update_state() {
  local file="$1"
  local key="$2"
  local value="$3"
  local escaped

  escaped="$(printf '%q' "${value}")"

  if grep -q "^${key}=" "${file}"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "${file}"
  else
    printf '%s=%s\n' "${key}" "${escaped}" >> "${file}"
  fi
}

check_config_exists() {
  local config="$1"
  local output

  output="$(mgmt configurations get --name "${config}" 2>&1 || true)"

  if echo "${output}" | grep -qi "Configuration not found"; then
    echo "${output}"
    exit 1
  fi
}
active_request_count() {
  local mode="$1"
  local count=0
  local state_file
  local REQ_ID JOB_SCRIPT NB_NODES CONFIG CLUSTER LOG_FILE STATUS PID JOB_ID NODELIST

  for state_file in "${STATE_DIR}"/*.env; do
    [[ -f "${state_file}" ]] || continue

    STATUS=""
    # shellcheck disable=SC1090
    source "${state_file}"

    case "${mode}:${STATUS:-}" in
      creating:CREATING|creating:WAITING_FOR_NODES)
        count=$((count + 1))
        ;;
      active:CREATING|active:WAITING_FOR_NODES|active:SUBMITTED|active:RUNNING|active:DELETING)
        count=$((count + 1))
        ;;
    esac
  done

  echo "${count}"
}


janitor() {
  local state_file
  local actions=0
  local checked=0
  local REQ_ID JOB_SCRIPT NB_NODES CONFIG CLUSTER LOG_FILE STATUS PID JOB_ID NODELIST

  for state_file in "${STATE_DIR}"/*.env; do
    [[ -f "${state_file}" ]] || continue
    checked=$((checked + 1))

    REQ_ID=""
    CLUSTER=""
    STATUS=""
    PID=""
    JOB_ID=""

    # shellcheck disable=SC1090
    source "${state_file}"

    case "${STATUS:-}" in
      CREATING|WAITING_FOR_NODES)
        if [[ -n "${PID:-}" ]] && kill -0 "${PID}" 2>/dev/null; then
          continue
        fi

        echo "Found abandoned request ${REQ_ID}, deleting ${CLUSTER}"
        mgmt clusters delete --cluster "${CLUSTER}" || true
        update_state "${state_file}" STATUS FAILED_CLEANED
        actions=$((actions + 1))
        ;;

      SUBMITTED|RUNNING)
        [[ -n "${JOB_ID:-}" ]] || continue

        if squeue -j "${JOB_ID}" -h | grep -q .; then
          continue
        fi

        echo "Job ${JOB_ID} completed, deleting ${CLUSTER}"
        update_state "${state_file}" STATUS DELETING
        mgmt clusters delete --cluster "${CLUSTER}" || true
        update_state "${state_file}" STATUS DONE
        actions=$((actions + 1))
        ;;
    esac
  done

  if (( actions == 0 )); then
    echo "Janitor: nothing to do. Checked ${checked} state file(s)."
  else
    echo "Janitor: completed ${actions} cleanup action(s). Checked ${checked} state file(s)."
  fi
}

find_duplicate() {
  local requested_config="$1"
  local requested_nodes="$2"
  local state state_config state_nodes state_status

  for state in "${STATE_DIR}"/*.env; do
    [[ -f "${state}" ]] || continue

    state_config="$(grep '^CONFIG=' "${state}" | cut -d= -f2- | xargs)"
    state_nodes="$(grep '^NB_NODES=' "${state}" | cut -d= -f2- | xargs)"
    state_status="$(grep '^STATUS=' "${state}" | cut -d= -f2- | xargs)"

    case "${state_status}" in
      CREATING|WAITING_FOR_NODES|SUBMITTED|RUNNING)
        if [[ "${state_config}" == "${requested_config}" && "${state_nodes}" == "${requested_nodes}" ]]; then
          echo "${state}"
          return 0
        fi
        ;;
    esac
  done

  return 1
}

worker() {
  local state_file="$1"

  # shellcheck disable=SC1090
  source "${state_file}"

  local cluster_created=false

  on_error() {
    local rc=$?
    update_state "${state_file}" STATUS FAILED

    if [[ "${cluster_created}" == "true" ]]; then
      echo "Failure. Deleting cluster ${CLUSTER}"
      mgmt clusters delete --cluster "${CLUSTER}" || true
    fi

    exit "${rc}"
  }

  trap on_error ERR

  echo "Started worker at $(date)"
  echo "State file: ${state_file}"
  echo "Job script: ${JOB_SCRIPT}"
  echo "Config: ${CONFIG}"
  echo "Nodes: ${NB_NODES}"
  echo "Cluster: ${CLUSTER}"

  check_config_exists "${CONFIG}"

  update_state "${state_file}" STATUS CREATING
  echo "Creating cluster ${CLUSTER}"

  mgmt clusters create \
    --cluster "${CLUSTER}" \
    --instancetype "${CONFIG}" \
    --count "${NB_NODES}"

  cluster_created=true

  update_state "${state_file}" STATUS WAITING_FOR_NODES
  echo "Waiting for nodes from ${CLUSTER} to register in Slurm"

  NODELIST=""
  for _ in {1..120}; do
    NODELIST="$(
      mgmt nodes list \
        --fields "cluster_name=${CLUSTER}" \
        --columns hostname \
        --format json 2>/dev/null \
      | jq -r '.[]?.hostname' \
      | while read -r node; do
          sinfo -N -h -n "$node" -o "%N" 2>/dev/null || true
        done \
      | paste -sd, -
    )"

    COUNT="$(echo "${NODELIST}" | tr ',' '\n' | sed '/^$/d' | wc -l | tr -d ' ')"

    if [[ "${COUNT}" -ge "${NB_NODES}" ]]; then
      break
    fi

    sleep 30
  done

  [[ -n "${NODELIST}" ]] || {
    echo "Cluster was created, but no nodes registered in Slurm for ${CLUSTER}"
    exit 1
  }

  update_state "${state_file}" NODELIST "${NODELIST}"

  echo "Submitting job script: ${JOB_SCRIPT}"
  echo "Script checksum: $(sha256sum "${JOB_SCRIPT}" | awk '{print $1}')"
  echo "Script content at submit time:"
  sed -n '1,40p' "${JOB_SCRIPT}"
  JOB_ID="$(sbatch --parsable "${JOB_SCRIPT}")"

  update_state "${state_file}" JOB_ID "${JOB_ID}"
  update_state "${state_file}" STATUS RUNNING

  echo "Submitted Slurm job ${JOB_ID}"

  update_state "${state_file}" STATUS RUNNING

  echo "Worker finished. Cluster cleanup will be handled by janitor."
  echo "Run periodically:"
  echo "  $0 --janitor"
  echo "Done at $(date)"
}

if [[ "${1:-}" == "--worker" ]]; then
  shift
  worker "$1"
  exit 0
fi




if [[ "${1:-}" == "--janitor" ]]; then
  janitor
  exit 0
fi
FORCE=false
if [[ "${1:-}" == "--force" ]]; then
  FORCE=true
  shift
fi

JOB_SCRIPT="${1:-}"
[[ -n "${JOB_SCRIPT}" && -f "${JOB_SCRIPT}" ]] || {
  echo "Usage: perjob-submit [--force] job.sbatch"
  exit 1
}

JOB_SCRIPT="$(realpath "${JOB_SCRIPT}")"

NB_NODES="$(get_sbatch_value "--nodes" "${JOB_SCRIPT}")"
[[ -n "${NB_NODES}" ]] || NB_NODES="$(get_sbatch_value "-N" "${JOB_SCRIPT}")"

CONFIG="$(get_sbatch_value "--constraint" "${JOB_SCRIPT}")"
[[ -n "${CONFIG}" ]] || CONFIG="$(get_sbatch_value "-C" "${JOB_SCRIPT}")"

[[ -n "${NB_NODES}" ]] || {
  echo "Missing #SBATCH --nodes or #SBATCH -N in ${JOB_SCRIPT}"
  exit 1
}

[[ -n "${CONFIG}" ]] || {
  echo "Missing #SBATCH --constraint or #SBATCH -C in ${JOB_SCRIPT}"
  exit 1
}
echo "Parsed request:"
echo "  job_script=${JOB_SCRIPT}"
echo "  nodes=${NB_NODES}"
echo "  constraint=${CONFIG}"

check_config_exists "${CONFIG}"

janitor

ACTIVE_REQUESTS="$(active_request_count active)"
CREATING_REQUESTS="$(active_request_count creating)"

if (( ACTIVE_REQUESTS >= MAX_ACTIVE )); then
  echo "Too many active perjob requests: ${ACTIVE_REQUESTS}/${MAX_ACTIVE}"
  echo "Inspect:"
  echo "  ls ${STATE_DIR}"
  exit 1
fi

if (( CREATING_REQUESTS >= MAX_CREATING )); then
  echo "Too many perjob clusters currently being created: ${CREATING_REQUESTS}/${MAX_CREATING}"
  echo "Try again later."
  exit 1
fi

if duplicate_state="$(find_duplicate "${CONFIG}" "${NB_NODES}")"; then
  echo "A matching perjob request is already active:"
  echo "  state: ${duplicate_state}"

  if [[ "${FORCE}" != "true" ]]; then
    if [[ -t 0 ]]; then
      read -r -p "Submit another job with ${NB_NODES} nodes and constraint ${CONFIG}? [y/N] " answer
      [[ "${answer}" =~ ^[Yy]$ ]] || exit 1
    else
      echo "Non-interactive mode: use --force to submit anyway."
      exit 1
    fi
  fi
fi

REQ_ID="$(date +%Y%m%d%H%M%S)_$$"
CLUSTER="JOB_${REQ_ID}"
LOG_FILE="${LOG_ROOT}/${REQ_ID}.log"
STATE_FILE="${STATE_DIR}/${REQ_ID}.env"

SCRIPT_COPY="${LOG_ROOT}/${REQ_ID}.sbatch"
cp "${JOB_SCRIPT}" "${SCRIPT_COPY}"
JOB_SCRIPT="${SCRIPT_COPY}"

{
  printf 'REQ_ID=%q\n' "${REQ_ID}"
  printf 'JOB_SCRIPT=%q\n' "${JOB_SCRIPT}"
  printf 'NB_NODES=%q\n' "${NB_NODES}"
  printf 'CONFIG=%q\n' "${CONFIG}"
  printf 'CLUSTER=%q\n' "${CLUSTER}"
  printf 'LOG_FILE=%q\n' "${LOG_FILE}"
  printf 'STATUS=%q\n' "QUEUED"
} > "${STATE_FILE}"

nohup "$0" --worker "${STATE_FILE}" >> "${LOG_FILE}" 2>&1 &
PID="$!"

update_state "${STATE_FILE}" PID "${PID}"
update_state "${STATE_FILE}" STATUS CREATING

echo "Started perjob submission in background"
echo "  request: ${REQ_ID}"
echo "  pid: ${PID}"
echo "  log: ${LOG_FILE}"
echo "  state: ${STATE_FILE}"
echo
echo "Monitor with:"
echo "  tail -f ${LOG_FILE}"
