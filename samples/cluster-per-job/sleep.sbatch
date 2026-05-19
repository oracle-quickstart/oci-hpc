#!/bin/sh
#SBATCH --nodes 2
#SBATCH --exclusive
#SBATCH --job-name testperjob
#SBATCH --constraint perjob

echo $SLURM_JOB_ID

sleep 1000
