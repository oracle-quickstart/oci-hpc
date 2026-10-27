#!/usr/bin/bash
f=$(mktemp)
HOST=$1
ssh $HOST /usr/sbin/ip -j addr | jq  -r '.[] | select(.ifname | test("rdma")) | .ifname + " " + .addr_info[0].local' > $f
while read -r l ; do
  i=$(echo $l | awk '{print $1}')
  ip=$(echo $l | awk '{print $2}')
  ping -qI $i $ip -c1 ; done < $f
rm -rf $f