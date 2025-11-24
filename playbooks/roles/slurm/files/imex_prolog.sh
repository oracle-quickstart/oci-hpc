#!/usr/bin/env bash

shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)
if [ ${shape} = "BM.GPU.GB200.4" ] || [ ${shape} = "BM.GPU.GB200-v2.4" ] || ${shape} = "BM.GPU.GB300.4" ]; then

    {
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

    for i in `sudo scontrol show hostname ${SLURM_NODELIST}`
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

    echo "Waiting for NVIDIA domain status to be UP..."
    count=0
    while true; do
        status=$(sudo nvidia-imex-ctl -N | grep Domain | awk '{print $3}')
        echo $status
        if [[ "$status" == "UP" ]]; then
            echo "Domain is UP!"
            break
        fi
        if [[ $count -gt 20 ]]; then
           echo "Max count is exhausted"
           break
        fi
        echo sleeping
        sleep 2
        count=$((count+1))
    done
    sudo nvidia-imex-ctl -N

    LOCAL_IP=$(hostname -I | awk '{print $1}')
    IMEX_OUTPUT=$(nvidia-imex-ctl -N)

    NODE_INFO=$(echo "$IMEX_OUTPUT" | awk -v ip="$LOCAL_IP" '$4 == ip {print $2, $4, $6}')
    NODE_INDEX=$(echo "$NODE_INFO" | awk '{gsub("#", "", $1); print $1}')
    NODE_STATUS=$(echo "$NODE_INFO" | awk '{print $3}')

    echo "Node Index: $NODE_INDEX"
    echo "Node Status: $NODE_STATUS"

    if [ "$NODE_STATUS" = "READY" ]; then
        echo "Local node is READY."
    else
        echo "Local node is NOT ready."
        exit 1
    fi

    MATRIX=$(echo "$IMEX_OUTPUT" | awk '/^ Nodes From\\To/{flag=1; next} /^Domain State:/{flag=0} flag')
    TOTAL_NODES=$(echo "$MATRIX" | wc -l | awk '{print $1}')
    MISSING_LIMIT=3
    UNHEALTHY_FILE=$(mktemp)

    echo ""
    echo "Node Connectivity Summary:"
    LOCAL_LINE=$(echo "$MATRIX" | awk -v idx="$NODE_INDEX" '$1 == idx')
    echo $LOCAL_LINE
    if [ -n "$LOCAL_LINE" ]; then
      CONNECTIONS=$(echo "$LOCAL_LINE" | grep -o 'C' | wc -l)
      MISSING=$(( TOTAL_NODES - CONNECTIONS ))
      echo "Node $NODE_INDEX: $CONNECTIONS connections, $MISSING missing"

      if [ "$MISSING" -gt "$MISSING_LIMIT" ]; then
        echo "1" > "$UNHEALTHY_FILE"
      fi
    else
      echo "❌ Could not find local node ($NODE_INDEX) in matrix"
      echo "1" > "$UNHEALTHY_FILE"
    fi

    echo ""
    if [ -s "$UNHEALTHY_FILE" ]; then
        echo "❌ Rack Health: NOT HEALTHY (more than $MISSING_LIMIT missing connections)"
        exit 1
    else
        echo "✅ Rack Health: HEALTHY"
    fi

    rm -f "$UNHEALTHY_FILE"
    } > "/var/log/slurm/imex_prolog_${SLURM_JOB_ID}.log" 2>&1
fi