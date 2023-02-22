#!/bin/bash 

# Run on 1 GPU node only

mpivars_path=`ls /usr/mpi/gcc/openmpi-*/bin/mpivars.sh`
source $mpivars_path

if [[ "$mpivars_path" == "" ]]; then echo "Could not find MPIPATH"; exit; fi


cd /home/opc
git clone https://github.com/NVIDIA/nccl-tests.git
cd nccl-tests/
make MPI=1 MPI_HOME=$MPI_HOME  CUDA_HOME=/usr/local/cuda

