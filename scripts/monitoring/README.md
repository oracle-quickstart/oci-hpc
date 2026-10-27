# Monitoring scripts

These scripts inspect local monitoring services or create data used to check Slurm exporters.

- `exporter_usage_stats.sh <service_name> <output.csv>` records systemd CPU and memory usage for a service over 24 hours.
- `ping.sh <host>` checks RDMA interface reachability for a remote host.
- `prometheus_usage_stats.sh` prints local Prometheus TSDB size, ingestion, and growth information.
- `test_slurm_exporters.sh` creates Slurm accounting, job, user, and reservation data for exporter testing.

`prometheus_usage_stats.sh` assumes Prometheus is reachable at `http://localhost:9090`. `test_slurm_exporters.sh` changes Slurm state by creating test objects and jobs, so run it only in an approved test environment.
