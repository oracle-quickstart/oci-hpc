#!/bin/bash
set -e
sudo mst start

BUSIDS=""

shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.B4.8\" ]
then
  BUSIDS="0000:0c:00.0 0000:16:00.0 0000:47:00.0 0000:4b:00.0 0000:89:00.0 0000:93:00.0 0000:c3:00.0 0000:d1:00.0"
elif [ $shape == \"BM.GPU4.8\" ]
then
  BUSIDS="0000:48:00.0 0000:c3:00.0 0000:d1:00.0 0000:8a:00.0 0000:94:00.0 0000:4c:00.0 0000:0c:00.0 0000:16:00.0"
fi

#echo "********************** Updating firmware settings **********************"
for BUS in $BUSIDS; do
  sudo mlxconfig -d $BUS -y set MAX_ACC_OUT_READ=44
  sudo mlxconfig -d $BUS query  MAX_ACC_OUT_READ
done
