#!/bin/bash

cd /opt/oci-hpc/samples/
for directory in `ls -d */ ` ;
do
  echo $directory
  sudo chmod +x $directory/*.sh
done;

cp nccl_compile/compile.sh /home/opc/
cp gpu/*.sbatch /home/opc/
cp /opt/oci-hpc/bin/node_ordering_by_rack.py /home/opc/

