#!/bin/sh
#SBATCH -n 72
#SBATCH --ntasks-per-node 36
#SBATCH --exclusive
#SBATCH --job-name sleep_job
#SBATCH --constraint cluster-size-2,BM.HPC2.36


cd /nfs/scratch
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID
MACHINEFILE="hostfile"

# Generate Machinefile for mpi such that hosts are in the same
#  order as if run via srun
#
srun -N$SLURM_NNODES -n$SLURM_NNODES  hostname  > $MACHINEFILE
sed -i 's/$/:36/' $MACHINEFILE

cat $MACHINEFILE
# Run using generated Machine file:
sleep 1000
