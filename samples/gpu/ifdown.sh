#!/bin/bash

NICS=""
shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.B4.8\" ]
then
  NICS="enp71s0f0 enp71s0f1 enp75s0f0 enp75s0f1 enp12s0f0 enp12s0f1 enp22s0f0 enp22s0f1 enp195s0f0 enp195s0f1 enp209s0f0 enp209s0f1 enp137s0f0 enp137s0f1 enp147s0"
elif [ $shape == \"BM.GPU4.8\" ]
then
  NICS="enp72s0f0 enp72s0f1 enp76s0f0 enp76s0f1 enp12s0f0 enp12s0f1 enp22s0f0 enp22s0f1 enp195s0f0 enp195s0f1 enp209s0f0 enp209s0f1 enp138s0f0 enp138s0f1 enp148s0f0 enp148s0f1"
fi
echo $NICS

for NIC in $NICS; do 
  echo "running ifdown $NIC ..."
  sudo ifdown $NIC
done 

