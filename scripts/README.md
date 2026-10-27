# Operational scripts

This directory contains manually run cluster operations, diagnostics, and repository-maintenance tools. These scripts are separate from the Terraform, cloud-init, and Ansible deployment paths. Read the README in the relevant directory before running a script.

## Directories

- `cluster-management/` manages OCI instance configurations used by Cluster Networks and GPU Memory Clusters.
- `collect_metadata/` collects instance and host metadata over SSH.
- `development/` generates checked-in project artifacts.
- `diagnostics/` collects health data and runs GPU, firmware, and RDMA checks.
- `ldap/` migrates LDAP data and manages Grafana LDAP authentication.
- `monitoring/` checks monitoring services and Slurm exporters.
- `node-configuration/` applies host-level configuration changes.
