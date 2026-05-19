#!/bin/bash
#
# Shared bootstrap helpers for setup scripts: logging traps and mkdir-based
# install locks used to coordinate one-time work across cluster nodes.

bootstrap_script_name=""

# Default wait times for cluster-wide one-time installs.
: "${BOOTSTRAP_ANSIBLE_INSTALL_LOCK_TIMEOUT_SECONDS:=1200}"
: "${BOOTSTRAP_PYTHON_INSTALL_LOCK_TIMEOUT_SECONDS:=1800}"
readonly BOOTSTRAP_ANSIBLE_INSTALL_LOCK_TIMEOUT_SECONDS
readonly BOOTSTRAP_PYTHON_INSTALL_LOCK_TIMEOUT_SECONDS

# Emit uniform error/exit records so bootstrap failures are easy to correlate.
_bootstrap_log_error() {
  local rc="$1"
  local line="$2"
  local cmd="$3"
  local script_name="${bootstrap_script_name:-$(basename "$0")}"

  echo "ERROR script=${script_name} line=${line} rc=${rc} cmd=${cmd}"
}

_bootstrap_log_exit() {
  local rc="$1"
  local script_name="${bootstrap_script_name:-$(basename "$0")}"

  echo "EXIT script=${script_name} rc=${rc}"
}

setup_bootstrap_error_trap() {
  bootstrap_script_name="${1:-$(basename "$0")}"

  trap '_bootstrap_log_error $? $LINENO "$BASH_COMMAND"' ERR
}

setup_bootstrap_traps() {
  setup_bootstrap_error_trap "${1:-$(basename "$0")}"
  trap '_bootstrap_log_exit $?' EXIT
}

run_with_retry() {
  local max_attempts="${1}"
  local wait_time="${2}"
  local command_name="${3}"
  shift 3
  local attempt
  local rc=0

  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    echo "Attempt ${attempt} of ${max_attempts}: ${command_name}"
    if "$@"; then
      echo "${command_name} succeeded!"
      return 0
    else
      rc=$?
    fi

    echo "${command_name} failed."
    if (( attempt < max_attempts )); then
      echo "Retrying in (${wait_time})s ..."
      sleep "${wait_time}"
    fi
  done

  echo "Max attempts (${max_attempts}) reached for ${command_name}. Giving up."
  return "${rc}"
}

# Coordinate long one-time installs: uses the caller's marker_* globals, sets
# acquired=true only for the node that should perform the install, and lets
# other nodes wait for the success marker.
acquire_install_lock() {
  local install_name="${1}"
  local timeout_seconds="${2}"
  local timeout
  local setup_hostname

  # Expected globals:
  # - marker_install
  # - marker_in_progress
  # - marker_in_progress_hostname
  # - acquired
  acquired=false
  timeout=$(( SECONDS + timeout_seconds ))
  echo "Starting ${install_name} install lock loop timeout_seconds=${timeout_seconds}"

  while (( SECONDS < timeout )); do
    if [[ -f "${marker_install}" ]]; then
      echo "${install_name} already installed and set up; found ${marker_install}"
      break
    fi

    echo "Attempting to acquire install lock ${marker_in_progress}"
    if mkdir "${marker_in_progress}" 2>/dev/null; then
      acquired=true
      hostname > "${marker_in_progress_hostname}" || true
      echo "Acquired install lock; hostname recorded in ${marker_in_progress_hostname}"

      # Another node may have finished between our success check and lock acquisition.
      if [[ -f "${marker_install}" ]]; then
        echo "Success marker appeared after lock acquisition; releasing lock"
        rm -rf "${marker_in_progress}"
        acquired=false
      fi
      break
    fi

    setup_hostname="unknown"
    if [[ -f "${marker_in_progress_hostname}" ]]; then
      setup_hostname=$(cat "${marker_in_progress_hostname}" 2>/dev/null || true)
      [[ -n "${setup_hostname}" ]] || setup_hostname="unknown"
    fi

    echo "${install_name} already being installed by ${setup_hostname}; waiting 15s remaining=$(( timeout - SECONDS ))s"
    sleep 15
  done
}

# Protect a short critical section: acquire a mkdir lock, run one command, then
# release the lock without reading install markers or changing acquired.
run_with_mkdir_lock() {
  local lock_dir="${1}"
  local lock_name="${2}"
  local timeout_seconds="${3}"
  shift 3
  local timeout
  local lock_hostname
  local rc=0

  timeout=$(( SECONDS + timeout_seconds ))
  while (( SECONDS < timeout )); do
    if mkdir "${lock_dir}" 2>/dev/null; then
      hostname > "${lock_dir}/hostname" 2>/dev/null || true
      "$@" || rc=$?
      rm -rf "${lock_dir}"
      return "${rc}"
    fi

    lock_hostname="unknown"
    if [[ -f "${lock_dir}/hostname" ]]; then
      lock_hostname=$(cat "${lock_dir}/hostname" 2>/dev/null || true)
      [[ -n "${lock_hostname}" ]] || lock_hostname="unknown"
    fi

    echo "${lock_name} locked by ${lock_hostname}; waiting 1s remaining=$(( timeout - SECONDS ))s"
    sleep 1
  done

  echo "Timed out waiting for ${lock_name} lock: ${lock_dir}" >&2
  return 1
}
