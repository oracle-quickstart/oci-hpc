# Slurm submission samples

These are small Slurm job examples for checking scheduler submission and resource allocation.

- `sleep.sbatch` requests an exclusive CPU allocation and creates a hostfile.
- `sleep_gpu.sbatch` requests GPU resources and starts several short `srun` tasks.

Both files contain example partitions, constraints, paths, and resource counts. Update them to match the cluster configuration before submitting them.
