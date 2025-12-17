# HPC Cluster Stack

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)

## Introduction

This Terraform stack deploys a high-performance computing cluster with compute nodes, either CPU or GPU, and management nodes residing in a [Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) (VCN).
It makes use of different OCI services described in the section [cloud services used](#cloud-services-used).
Different storage solutions can also be added.
It is configured and deployed using the [Oracle Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm) managed service.

The following diagram shows the target architecture:

![Target architecture deployed via this Terraform stack.](/images/architecture_diagram.png)

## Prerequisites

Please ensure that you have setup all required prerequisites for successfully deploying the stack. For details, follow [this guide](/documentation/Prerequisites.md).

## Documentation

The information to deploy, use and understand the structure of the deployed infrastructure can be found in the [documentation section](/documentation/README.md).

## Contributing

This project welcomes contributions from the community. Before submitting a pull request, please [review our contribution guide](./CONTRIBUTING.md)

## Security

Please consult the [security guide](./SECURITY.md) for our responsible security vulnerability disclosure process

## License

Copyright (c) 2018-2020 Oracle and/or its affiliates.

Released under the Universal Permissive License v1.0 as shown at
<https://oss.oracle.com/licenses/upl/>.