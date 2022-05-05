#!/bin/bash 

# Run on 1 GPU node only

if [ -f /usr/mpi/gcc/openmpi-4.1.0rc5/bin/mpivars.sh ]; then
  source /usr/mpi/gcc/openmpi-4.1.0rc5/bin/mpivars.sh
  MPI_HOME=/usr/mpi/gcc/openmpi-4.1.0rc5
else
  source /usr/mpi/gcc/openmpi-4.0.3rc4/bin/mpivars.sh
  MPI_HOME=/usr/mpi/gcc/openmpi-4.0.3rc4
fi


cd /home/opc
git clone https://github.com/NVIDIA/nccl-tests.git
cd nccl-tests/
make MPI=1 MPI_HOME=$MPI_HOME  CUDA_HOME=/usr/local/cuda

