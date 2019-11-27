#!/bin/bash
#SBATCH --time=01:00:00 # WALLTIME
#SBATCH -N 2 # Number of nodes
#SBATCH -n 8 # Number of cores/processors
#SBATCH -o intel-mpi-%j.log
#SBATCH -p queue
#SBATCH --job-name intel-mpi-test # job name
echo "Node list is" $SLURM_NODELIST
### testing mpd ###
module load intel_mpi
########
srun --mpi=pmi2 ./a.out
