#!/bin/sh
shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ "${shape}" = \"BM.GPU.H100.8\" ]
then
    sudo python3 /opt/oci-hpc/healthchecks/check_h100_setup.py --slurm > /tmp/latest_healthcheck.log 2>&1
    DRAIN_MSG=`cat /tmp/latest_healthcheck.log | grep "Healthcheck::"`
    if [ "$DRAIN_MSG" != "" ]
    then
        scontrol update nodename=`hostname` state=drain reason="${DRAIN_MSG}"
    fi
fi
