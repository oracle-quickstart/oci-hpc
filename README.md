# HPC Cluster Stack

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)

## Introduction

This Terraform stack deploys a high-performance computing cluster with compute nodes, either CPU or GPU, and management nodes residing in a [Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) (VCN).
It makes use of different OCI services described in the section [cloud services used](#cloud-services-used).
Different storage solutions can also be added.
It is configured and deployed using the [Oracle Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm) managed service.

The following diagram shows the target architecture:

![Target architecture deployed via this Terraform stack.](/images/architecture_diagram.png)

## Documentation

The information to deploy, use and understand the structure of the deployed infrastructure can be found in [documentation section](/documentation/README.md).