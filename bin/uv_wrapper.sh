#!/bin/bash

# Wrapper around `uv`, picking up the architecture apropriate installation
# location.

source $(dirname "${0}")/setup_environment.sh
source "${UV_INSTALL_DIR}/env"

exec uv "$@"
