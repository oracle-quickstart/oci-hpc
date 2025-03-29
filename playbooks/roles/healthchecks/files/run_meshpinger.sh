#!/bin/bash

export WRAPPER_BIN="$0"
export WRAPPER_ENV="OCI_HPC_STACK"
date

eval "$(ssh-agent -s)" >/dev/null ; ssh-add ~/.ssh/id_rsa >/dev/null

# Run meshpinger
/opt/oci-hpc/healthchecks/meshpinger_bm/run_meshpinger "$@"