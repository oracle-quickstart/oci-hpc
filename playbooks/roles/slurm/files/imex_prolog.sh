#!/usr/bin/env bash

shape=$(curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape)
if [ ${shape} = "BM.GPU.GB200.4" ]; then

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
    sleep 3
    } > "/var/log/slurm/imex_prolog_${SLURM_JOB_ID}.log" 2>&1
fi