#!/bin/bash

# Run on 1 GPU node only

mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`

if [[ "$mpivars_path" == "" ]]; then
    mpivars_path=`ls /opt/openmpi-*/bin/mpivars.sh`
fi

if [[ "$mpivars_path" == "" ]]; then
    echo "Could not find MPIPATH"; exit; fi

source $mpivars_path
MPI_HOME=${mpivars_path%%/bin*}

source /etc/os-release
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then
    cd /home/opc
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
    cd /home/ubuntu
fi


git clone https://github.com/NVIDIA/nccl-tests.git
cd nccl-tests/
make MPI=1 MPI_HOME=$MPI_HOME  CUDA_HOME=/usr/local/cuda

