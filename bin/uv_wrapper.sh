#!/bin/bash

# Wrapper around `uv`, picking up the architecture appropriate installation
# location. `run-venv` runs a command in the stack-managed oci virtualenv.

source "$(dirname "${0}")/setup_environment.sh"
source "${UV_INSTALL_DIR}/env"

if [[ "${1:-}" == "run-venv" ]]; then
  shift

  if [[ ! -x "${VENV_PATH}/bin/python3" ]]; then
    echo "Managed Python virtualenv is unavailable: ${VENV_PATH}" >&2
    exit 1
  fi

  export VIRTUAL_ENV="${VENV_PATH}"
  exec uv run --active "$@"
fi

exec uv "$@"
