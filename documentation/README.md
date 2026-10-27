# Documentation

This documentation is organized by task and audience.

## Deployers

- [Prerequisites, IAM policies, supported operating systems, and images](Prerequisites.md)
- [Stack configuration and deployment](Setup.md)
- [Cluster usage, resizing, and job submission](Userguide.md)
- [Technical background and deployment workflow](Background.md)

## Architects and administrators

- [Architecture overview](Architecture-Overview.md)
- [Sequence diagram: Terraform provisioning, node bootstrap, event, and management flows](architecture-sequence-diagram.md)
- [Cluster Lifecycle](Background.md)
- [Stack configuration](Setup.md)
- [Monitoring architecture and configuration](Monitoring.md)
- [GB200/GB300 memory-fabric deployments](GraceBlackwell-based-shapes.md)
- [DGXC benchmarking](DGXC.md)
- [Slurm monitoring metrics decision record](adr-slurm-monitoring-mysql-for-high-granularity-metrics.md)
- [Package versioning decision record](adr-versioning.md)


## Operators

- [Cluster management CLI (`mgmt`)](mgmt-cli.md)
- [Instance maintenance events and policy](Maintenance-Events.md)
- [Monitoring and alerting](Monitoring.md)
- [Centralized logging and troubleshooting](Troubleshooting.md)

## Runbooks

- [Create a Slurm GPU partition](Slurm-Partition-Runbook.md)
- [Diagnose and resolve Slurm issues](Slurm-Troubleshooting-Runbook.md)
- [Run passive, active, multi-node, and NCCL health checks](Healthcheck-NCCL-Runbook.md)
- [Recover or reconfigure local NVMe RAID](LocaldiskRecovery.md)

## Contributors

- [Contribution guide](../CONTRIBUTING.md)
- [Security guide](../SECURITY.md)

Commands are examples and must be reviewed for the target tenancy, operating
system, image, and topology. Values in `variables.tf`, `schema.yaml`, and the
OCI console remain authoritative for a particular release.
