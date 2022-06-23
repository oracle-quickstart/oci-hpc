#!/bin/bash

#
# A little waiter function to make sure all the nodes are up before we start configure
#

echo "Checking For SSH"

ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
rm $2

for host in $(cat $1) ; do
  r=0
  echo "validating connection to: ${host}"
  if [[ `ssh ${ssh_options} -o ConnectTimeout=15 opc@${host} uptime | grep load | wc -l` > 0 ]] ;
  then
    echo ${host} >> $2
  fi
done