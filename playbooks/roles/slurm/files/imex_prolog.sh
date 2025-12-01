#!/usr/bin/env bash

set -ex

shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)
if [ ${shape} = "BM.GPU.GB200.4" ] || [ ${shape} = "BM.GPU.GB200-v2.4" ] || [ ${shape} = "BM.GPU.GB200-v3.4" ] || ${shape} = "BM.GPU.GB300.4" ]; then

  sudo --preserve-env=SLURM_NODELIST,SLURM_JOB_ID bash <<'SUDO'
    set -ex
    #Clean the config file in case the service gets started by accident
    > /etc/nvidia-imex/nodes_config.cfg

    NVIDIA_IMEX_START_TIMEOUT=60
    IMEX_CONN_WAIT_TIMEOUT=70
    NVIDIA_IMEX_STOP_TIMEOUT=15

    #clean up prev connection
    set +e
    timeout $NVIDIA_IMEX_STOP_TIMEOUT systemctl stop nvidia-imex
    pkill -9 nvidia-imex
    set -e

    #update peer list
    current_host=`hostname`
    current_switch=`scontrol show topology ${current_host} | grep Level=0 | awk '{print $1}'`

    for i in `scontrol show hostname ${SLURM_NODELIST}`
    do
      ip=`scontrol -a show node $i -o | sed 's/^.* NodeAddr=\([^ ]*\).*/\1/'`
      switchname_add=`scontrol show topology $i | grep Level=0 | awk '{print $1}'`

      if [ ${current_switch} = ${switchname_add} ]; then
        echo "${current_switch} ${ip}" >> /tmp/imex.log
        echo ${ip} >> /etc/nvidia-imex/nodes_config.cfg
      fi
    done
    #rotate server port to prevent race condition
    NEW_SERVER_PORT=$((${SLURM_JOB_ID} % 16384 + 33792))
    sed -i "s/SERVER_PORT.*/SERVER_PORT=${NEW_SERVER_PORT}/" /etc/nvidia-imex/config.cfg

    #enable imex-ctl on all nodes so you can query imex status with: nvidia-imex-ctl -a -q
    sed -i "s/IMEX_CMD_PORT.*/IMEX_CMD_PORT=50005/" /etc/nvidia-imex/config.cfg
    sed -i "s/IMEX_CMD_ENABLED.*/IMEX_CMD_ENABLED=1/" /etc/nvidia-imex/config.cfg

    #set timeouts for start
    sed -i "s/IMEX_CONN_WAIT_TIMEOUT.*/IMEX_CONN_WAIT_TIMEOUT=${IMEX_CONN_WAIT_TIMEOUT}/" /etc/nvidia-imex/config.cfg
    timeout $NVIDIA_IMEX_START_TIMEOUT systemctl start nvidia-imex
SUDO

  echo "Waiting for NVIDIA domain status to be UP"
  count=0
  while true; do
    status=$(nvidia-imex-ctl -N -j | jq -r '.status')
    if [[ "$status" == "UP" ]]; then
      echo "Domain is UP!"
      break
    fi
    if [[ $count -gt 20 ]]; then
      echo " Max count is exhausted without domain coming up"
      nvidia-imex-ctl -N
      exit 1
    fi
    echo -n "."
    sleep 2
    count=$((count+1))
  done

  export LOCAL_IP=$(hostname -I | awk '{print $1}')
  export IMEX_OUTPUT_JSON=$(nvidia-imex-ctl -N -j)

  export NODE_IDX=$(jq \
    -r --arg node_ip "$LOCAL_IP" -n '
      env.IMEX_OUTPUT_JSON | fromjson
      | .nodes
      | to_entries[]
      | select(.value.host == $node_ip)
      |     .key')
  NODE_STATUS=$(jq \
    -r --arg node_idx "$NODE_IDX"  -n '
      env.IMEX_OUTPUT_JSON | fromjson
      | .nodes
      | to_entries[]
      |  select(.key == $node_idx)
      |     .value.status')
  echo "Node Index: $NODE_IDX"
  echo "Node Status: $NODE_STATUS"

  if [ "$NODE_STATUS" = "READY" ]; then
    echo "Local node is READY."
  else
    echo "Local node is NOT ready."
    exit 1
  fi

  N_NODES=$(jq \
    -r -n '
      env.IMEX_OUTPUT_JSON | fromjson
      | .nodes
      | length')
  MISSING_LIMIT=3

  N_CONNECTIONS=$(jq \
    -r --arg node_idx "$NODE_IDX" -n '
      env.IMEX_OUTPUT_JSON | fromjson
      | .nodes
      | to_entries[]
      | select(.key == $node_idx)
      |     .value.connections
      |     to_entries
      |     map(select(.value.status == "CONNECTED"))
      |         length')
  echo ""
  echo "Node Connectivity Summary:"
  jq -r --arg node_idx "$NODE_IDX"  -n '
    env.IMEX_OUTPUT_JSON | fromjson
    | .nodes
    | to_entries[]
    | select(.key == $node_idx)
    |     .value.connections'
  MISSING=$(( N_NODES - N_CONNECTIONS ))
  if [ "$MISSING" -gt "$MISSING_LIMIT" ]; then
    echo "❌ Rack Health: NOT HEALTHY ($MISSING connections missing)"
  else
    echo "✅ Rack Health: HEALTHY"
  fi
fi
