#!/bin/bash

#
# A little waiter function to make sure all the nodes are up before we start configure
#

echo "Waiting for SSH to come up" 

ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
for host in $(cat $1) ; do
  r=0 
  echo "validating connection to: ${host}"
  while ! ssh ${ssh_options} -o ConnectTimeout=30 opc@${host} uptime ; do
	if [[ $r -eq 10 ]] ; then 
		  execution=0
		  break
	fi 
	  echo "Still waiting for ${host}"
          sleep 30 
	  r=$(($r + 1))
  done
done
