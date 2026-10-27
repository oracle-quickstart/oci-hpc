# RDMA diagnostics

These scripts run active RDMA or NCCL tests between compute nodes. They need SSH access to the target nodes and the relevant RDMA and GPU test tools installed on those nodes.

- `ib_write_bw.sh <server> [client] [device]` runs `ib_write_bw` across supported devices.
- `ib_write_lat.sh <server> [client]` runs `ib_write_lat` across supported devices.
- `runNCCL_on_hostPair.sh <hostfile>` tests host pairs with the GPU communication sample and writes pass, fail, retry, and log files in the current directory.

These commands drive fabric traffic and can consume GPU, CPU, and network capacity. Reserve the target nodes and avoid running them with production workloads.
