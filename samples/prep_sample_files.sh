#!/bin/bash

cd /opt/oci-hpc/samples/
for directory in `ls -d */ ` ;
do
  echo $directory
  sudo chmod +x $directory/*.sh
done;

cp nccl_compile/compile.sh ~
cp gpu/*.sbatch ~
cp /opt/oci-hpc/bin/node_ordering_by_rack.py ~

