# Diagnostics

These tools collect evidence or run health checks for deployed clusters. Several use SSH, require a hostfile, or run commands with elevated privileges. Start with the least disruptive check and save output with the related incident data.

- `check_firmware_version.sh` reads InfiniBand firmware versions from hosts in a hostfile.
- `collect_logs.py` gathers diagnostic logs, including `sosreport` and NVIDIA bug reports.
- `gpu_throttle.sh` reports NVIDIA GPU clocks, temperature, power, and throttle state.
- `h100_script.py` gathers H100 diagnostic data from hosts in a hostfile.
- `ncclscout.py` runs pairwise NCCL or RCCL communication checks and writes test logs.
- `rdma/` contains active RDMA bandwidth, latency, and pairwise NCCL tests.

Do not run active communication tests alongside production jobs unless their load and node allocation have been approved.
