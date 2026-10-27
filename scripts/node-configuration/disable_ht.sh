#!/bin/bash

# argument: 1="0" turn off hyper threading, "1" turn it on.
THREADS=`lscpu | grep -E '^Thread|^Core|^Socket|^CPU\(' | head -1 | awk '{ print $2 }'`
CORES=`expr $THREADS / 2`

if [[ $# -ne 1 ]]; then
    echo 'One argument required. 0 to turn off hyper-threading or'
    echo '1 to turn hyper-threading back on'
    exit 1
fi

echo Thread pairs before change
cat /sys/devices/system/cpu/cpu*/topology/thread_siblings_list | sort --unique --numeric-sort
echo

for k in `seq $CORES $THREADS`; do 
    echo $1 > /sys/devices/system/cpu/cpu$k/online;
done

grep "" /sys/devices/system/cpu/cpu*/topology/core_id

grep -q '^flags.*[[:space:]]ht[[:space:]]' /proc/cpuinfo && \
    echo "Hyper-threading is supported"

grep -E 'model|stepping' /proc/cpuinfo | sort -u

echo Thread pairs after change
cat /sys/devices/system/cpu/cpu*/topology/thread_siblings_list | sort --unique --numeric-sort
echo