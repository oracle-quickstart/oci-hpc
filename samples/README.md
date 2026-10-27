# Samples

This directory contains example Slurm jobs and cluster workflows. They are starting points, not supported production configurations. Review resource requests, paths, and constraints before using an example on a cluster.

## Directories

- `cluster-per-job/` contains a wrapper and job file for creating a temporary cluster for each job.
- `gpu/` contains NCCL and RCCL examples for multi-node GPU communication tests.
- `rdma-tuning_A100-shapes/` contains A100, B4, and GPU4 PCIe and RDMA tuning scripts.
- `submit/` contains small CPU and GPU Slurm submission examples.

The RDMA tuning scripts require elevated privileges and can alter PCIe or NIC settings. They are shape-specific and should be validated in a maintenance window before wider use.
