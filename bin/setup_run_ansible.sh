#!/bin/bash
set -Eeuo pipefail

# --- Bootstrap virtualenv ---
source "${UV_INSTALL_DIR}/env"
source "${VENV_PATH}/bin/activate"

# --- Argument validation ---
inventory="${1:-}"
playbook="${2:-}"

if [[ -z "${inventory}" || -z "${playbook}" ]]; then
    echo "usage: $(basename "${0}") <inventory> <playbook>"
    exit 1
fi

# --- Log file setup ---
modified_hostname=$(curl -fsL --retry 5 --retry-delay 2 -H "Authorization: Bearer Oracle" http://169.254.169.254/opc/v2/instance/displayName 2>/dev/null || true)
if [[ -z "${modified_hostname}" || "${modified_hostname}" == "null" ]]; then
    modified_hostname=$(hostname)
fi
log=/config/logs/${modified_hostname}.log
mkdir -p "$(dirname "${log}")"

timestamp_log() {
    local line
    while IFS= read -r line; do
        printf "%s\n" "${line}"
        printf '[%(%F %T)T] %s\n' -1 "${line}" >> "${log}"
    done
}

# --- Smoke-test installations in parallel ---
run_smoke_test() {
    local name="${1}"
    shift

    if "$@" 2>&1 | timestamp_log; then
        return 0
    fi

    echo "${name} smoke test failed" | timestamp_log
    return 1
}

echo "Testing Python and Ansible installations" | timestamp_log
run_smoke_test "Ansible" "${VENV_PATH}/bin/ansible" localhost -c local -m ping &
ansible_smoke_pid=$!
run_smoke_test "Python" "${VENV_PATH}/bin/python" -c "import uvicorn" &
python_smoke_pid=$!

smoke_rc=0
if ! wait "${ansible_smoke_pid}"; then
    smoke_rc=1
fi
if ! wait "${python_smoke_pid}"; then
    smoke_rc=1
fi
if [[ "${smoke_rc}" -ne 0 ]]; then
    echo "Smoke tests failed. Giving up." | timestamp_log
    exit 1
fi

# --- Retry loop with exponential backoff ---
max_attempts=6
wait_time=10
for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    echo "Attempt $attempt of $max_attempts: Configuring the node" | timestamp_log
    if "${VENV_PATH}/bin/ansible-playbook" -i "${inventory}" "${playbook}" 2>&1 | timestamp_log; then
        echo "Ansible succeeded!" | timestamp_log
        break
    fi
    echo "Ansible failed." | timestamp_log
    if [[ "${attempt}" -lt "${max_attempts}" ]]; then
        echo "Retrying in ($wait_time)s ..." | timestamp_log
        sleep "${wait_time}"
        (( wait_time *= 2 ))
    else
        echo "Max attempts ($max_attempts) reached. Giving up." | timestamp_log
        exit 1
    fi
done
