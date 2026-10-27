# OCI HPC/GPU Cluster Stack for Slurm

The OCI HPC/GPU Cluster Stack deploys and operates CPU and GPU high-performance
computing clusters on Oracle Cloud Infrastructure (OCI). It combines Terraform,
OCI Resource Manager, Ansible, Slurm, and OCI-native services to:

- **Provision** repeatable HPC infrastructure in a new or existing VCN.
- **Schedule** CPU and GPU workloads with Slurm, including optional high
  availability and federation.
- **Scale** clusters through cluster networks, compute clusters, instance pools,
  and standalone nodes.
- **Accelerate** workloads with RDMA, NVIDIA GPUs, AMD GPUs, and GPU
  memory-fabric configurations.
- **Integrate** OCI File Storage, Lustre, local NVMe, and Object Storage.
- **Operate** clusters with lifecycle automation, monitoring, health checks,
  alerting, and the `mgmt` management CLI.

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)

## Compatibility

| Component | Supported baseline |
| --- | --- |
| Terraform CLI | Version 1.2 or later |
| OCI Terraform provider | Version 7.19.0 or later |
| Operating systems &#x20; | See [prerequisites](documentation/Prerequisites.md#supported-operating-systems) |
| Compute images | See [image guidance](documentation/Prerequisites.md#images) |
| Compute shapes | Supports OCI compute shapes compatible with the selected image and OCI region. |
| Deployment methods | OCI Resource Manager or Terraform CLI |

Compatibility also depends on the selected region, availability domain,
service limits, image, compute shape, network, and storage configuration.

## Installation

OCI Resource Manager is the recommended deployment method. Use the deployment
button above or upload a release archive to Resource Manager. Terraform CLI
deployments are also supported when OCI authentication and all required input
variables are provided externally.

Deployment steps:

1. Review the [prerequisites](documentation/Prerequisites.md).
2. Configure the stack using the [setup guide](documentation/Setup.md).
3. Deploy the stack through Resource Manager or Terraform CLI.
4. Use the [management CLI](documentation/mgmt-cli.md) to validate and operate
   the resulting cluster.

> [!WARNING]
> This stack creates chargeable OCI resources. Review the Terraform plan and
> estimate the expected cost with the
> [Oracle Cloud Cost Estimator](https://www.oracle.com/cloud/costestimator.html)
> before applying it.

## Documentation

- **Getting started**
  - [Documentation overview](documentation/README.md)
  - [Prerequisites and supported images](documentation/Prerequisites.md)
  - [Stack configuration and deployment](documentation/Setup.md)
  - [Stack user guide](documentation/Userguide.md)
- **Architecture and configuration**
  - [Architecture overview](documentation/Architecture-Overview.md)
   - [Sequence diagram: Terraform provisioning, node bootstrap, event, and management flows](documentation/architecture-sequence-diagram.md)
  - [Cluster Lifecycle](documentation/Background.md)
  - [Monitoring and alerting](documentation/Monitoring.md)
  - [GB200/GB300 memory-fabric deployments](documentation/GraceBlackwell-based-shapes.md)
  - [DGXC benchmarking](documentation/DGXC.md)
- **Operations and runbooks**
  - [Cluster management CLI](documentation/mgmt-cli.md)
  - [Instance maintenance events and policy](documentation/Maintenance-Events.md)
  - [Create a Slurm GPU partition](documentation/Slurm-Partition-Runbook.md)
  - [Slurm troubleshooting](documentation/Slurm-Troubleshooting-Runbook.md)
  - [Run health checks and NCCL validation](documentation/Healthcheck-NCCL-Runbook.md)
  - [Recover local NVMe storage](documentation/LocaldiskRecovery.md)
  - [Centralized logging and troubleshooting](documentation/Troubleshooting.md)
- **Reference**
  - [Slurm monitoring metrics decision record](documentation/adr-slurm-monitoring-mysql-for-high-granularity-metrics.md)
  - [Package versioning decision record](documentation/adr-versioning.md)

## Examples

See the [`samples/`](samples/) directory for example configuration and workload
artifacts. Operational procedures, validation, and recovery steps are in the
[documentation overview](documentation/README.md).

## Help

- Open a [GitHub issue](https://github.com/oracle-quickstart/oci-hpc/issues) for
  bug reports, questions, or enhancement requests.
- Do not include credentials, private keys, authentication tokens, complete
  OCIDs, private addresses, or unsanitized logs in public issues.

## Contributing

Contributions from the community are welcome. Before submitting a pull request,
review the [contribution guide](CONTRIBUTING.md).

## Security

Report security vulnerabilities according to the [security guide](SECURITY.md).
Do not report vulnerabilities through a public GitHub issue.

## License

Copyright (c) 2018-2026 Oracle and/or its affiliates.

Released under the Universal Permissive License v1.0 as shown at
[https://oss.oracle.com/licenses/upl/](https://oss.oracle.com/licenses/upl/).
