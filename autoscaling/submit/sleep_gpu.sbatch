#!/bin/sh
#SBATCH --gpus 2
#SBATCH --job-name sleep_gpu
#SBATCH --constraint VM.GPU2.1


cd /nfs/scratch
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID

for i in 1 2 3 4 5; do
    srun --gpus 1 sleep 5 &
done
# Run using generated Machine file:
wait

sleep 5 