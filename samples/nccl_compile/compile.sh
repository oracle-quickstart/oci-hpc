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

USER=`whoami`

cd /home/$USER
rm -rf nccl-tests
git clone https://github.com/NVIDIA/nccl-tests.git
cd nccl-tests/
make MPI=1 MPI_HOME=$MPI_HOME  CUDA_HOME=/usr/local/cuda

