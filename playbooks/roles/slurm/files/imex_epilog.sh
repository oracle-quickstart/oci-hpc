#!/usr/bin/env bash

# Fetch the instance shape
shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)

if [ ${shape} = "BM.GPU.GB200.4" ] || [ ${shape} = "BM.GPU.GB200-v2.4" ] || [ ${shape} = "BM.GPU.GB200-v3.4" ] || [ ${shape} = "BM.GPU.GB300.4" ]; then

  set -ex
  #Clean the config file in case the service gets started by accident
  > /etc/nvidia-imex/nodes_config.cfg

  NVIDIA_IMEX_STOP_TIMEOUT=15

  #clean up connection

  set +e
  timeout $NVIDIA_IMEX_STOP_TIMEOUT systemctl stop nvidia-imex
  pkill -9 nvidia-imex
  set -e
fi