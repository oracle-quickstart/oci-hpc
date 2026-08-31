# Prerequisites and Consideration

## Service Limits

> [!WARNING]
> Be sure to have the appropriate Limits for each service that is used. In case you reach *limit exceeded*, you can create a [Service Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident-limit.htm).

## Policies

Different sets of Policies must be set to create the required authorizations.

### Policies to deploy the stack

The following policies are required to allon the stack service to create and manage resources in the tenancy.

```
allow service compute_management to use tag-namespace in tenancy
allow service compute_management to manage compute-management-family in tenancy
allow service compute_management to read app-catalog-listing in tenancy
allow group user to manage all-resources in compartment compartmentName
```

### Runtime policies

The stack runtime uses [Resource Principals](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm) for the Function and [Instance Principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm) for cluster nodes.

#### Stack-managed IAM (recommended)

Enable **Create Policies** in the Resource Manager **Identity** options to have the stack create the runtime dynamic group and its policies. The stack creates the policies needed for Functions, Queue, cluster resize operations, and boot-volume replacement. It also creates conditional policies for enabled features such as monitoring, Lustre, and GPU memory shapes.

By default, **Create Policies** is disabled so existing manual IAM configurations continue to work unchanged. The deployment policies above are still required to create and update the stack.

For manual runtime IAM, use the following sections only when **Create Policies** is disabled or when your organization manages IAM outside the stack. Keep the dynamic group and policies aligned with the cluster's enabled features and compartments.

### Policies for Functions

For the Function to manage resources in the compartment, create a [Dynamic Group](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/To_create_a_dynamic_group.htm) and grant it the required authorization.

Example:

1. Create a Dynamic Group named *fn_dg*:
```
ALL {resource.type = 'fnfunc', resource.compartment.id = 'ocid1.compartment.oc1..aaaXXXX'}
```
2. Create a Policy for this Dynamic Group:
```
Allow dynamic-group fn_dg to manage all-resources in compartment compartmentName
```

### Policies for Queue

In order to read messages from the OCI Queue service, the management and compute nodes must be part of a Dynamic Group with the necessary Policies (see [Instance Principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm)).

Example:

1. Create a Dynamic Group named *instance_principal*:
```
All {instance.compartment.id = 'ocid1.compartment.oc1..aaaXXXX'}
```
2. Create the Policies for this Dynamic Group:
```
Allow dynamic-group instance_principal to use queue-push in compartment CompartmentName
Allow dynamic-group instance_principal to use queue-pull in compartment CompartmentName
allow dynamic-group instance_principal to manage queues in compartment CompartmentName
```
If the Dynamic Group is created in a different Identity Domain, user must use `IdentityDomainName/DynamicGroupName` instead of `DynamicGroupName` in the Policies definition.

### Policies for resizing or adding clusters

As described when variables are specified, selecting Instance Principals as a way of authenticating nodes, user must generate a Dynamic Group that includes one or more Instances in a Compartment and all the Functions of the Compartment.

Example:

1. Create a Dynamic Group named *instance_principal*: 
```
All {instance.compartment.id = 'ocid1.compartment.oc1..aaaXXXX'}
```
If the Dynamic Group is created in a different Identity Domain, user must use `IdentityDomainName/DynamicGroupName` instead of `DynamicGroupName` in the Policies definition.

2. Create the Policies for this Dynamic Group:
```
Allow dynamic-group instance_principal to read app-catalog-listing in tenancy
Allow dynamic-group instance_principal to use tag-namespace in tenancy
```

3. Create additional Policies, either:
```
Allow dynamic-group instance_principal to manage compute-management-family in compartment compartmentName
Allow dynamic-group instance_principal to manage instance-family in compartment compartmentName
Allow dynamic-group instance_principal to use virtual-network-family in compartment compartmentName
Allow dynamic-group instance_principal to manage volume-family in compartment compartmentName
Allow dynamic-group instance_principal to manage dns in compartment compartmentName
```
or:
```
Allow dynamic-group instance_principal to manage all-resources in compartment compartmentName
```

### Policies for Host API

The Capacity Topology is created by default in the root Compartment. The folowing Policy must be created to access it: 
```
Allow dynamic-group instance_principal to manage compute-bare-metal-hosts in tenancy
```
For the GB series GPU, you will also need to add those policies: 
```
Allow any-user to use compute-hpc-islands in tenancy
Allow any-user to use compute-network-blocks in tenancy
Allow any-user to use compute-local-blocks in tenancy
Allow any-user to use compute-bare-metal-hosts in tenancy
Allow any-user to use compute-gpu-memory-fabrics in tenancy
```

### Policies for OCI Lustre Filesystem

When creating an OCI Lustre filesystem, the Lustre service needs network authorization:
```
Allow service lustrefs to use virtual-network-family in tenancy
```

### Policies for monitoring:

Integration with OCI services for monitoring purpose is optional and can be enabled by setting the variables:  - `alerting = true` to push Grafana alerts to OCI topics.
- `ingest_oci_metrics = true` to ingest OCI infrastructure metrics into Prometheus using OCI Service Connector Hub, Streaming and Telegraf.

If you have not set this policy in the previous step:  
```
Allow dynamic-group instance_principal to manage all-resources in compartment compartmentName
``` 

The policies needed are:

```
Allow dynamic-group instance_principal to use ons-family in compartment compartmentName
Allow dynamic-group instance_principal to use stream-family in compartment compartmentName
Allow dynamic-group instance_principal to read all-resources in compartment compartmentName

Allow any-user to read metrics in tenancy where all {request.principal.type = 'serviceconnector', request.principal.compartment.id = '<compartment_OCID>'}
Allow any-user to use stream-push in compartment id <target_stream_compartment_OCID> where all {request.principal.type='serviceconnector', request.principal.compartment.id='<compartment_OCID>'}
```

## Supported operating systems

This stack supports the operating systems and operating system combinations listed below. We can't guarantee any other combination. Mixing Ubuntu with Oracle Linux is not supported. Oracle Linux 8 is deprecated and will be phased out in a future release; new deployments should prefer Oracle Linux 9, Ubuntu 22.04, or Ubuntu 24.04.

|  Management nodes  |   Compute nodes   |
|--------------------|-------------------|
|         OL8        |         OL8       |
|         OL9        |         OL9       |
|    Ubuntu  22.04   |    Ubuntu 22.04   |
|    Ubuntu  24.04   |    Ubuntu 24.04   |

When switching to Ubuntu, user must ensure that the username is changed from `opc` to `ubuntu` in Oracle Resource Manager for both the management nodes and the compute nodes. 

## Images
To run on HPC/GPU nodes, you will need to use a custom image that has the appropriate drivers installed. The following link will allow you to build your own specific images: https://github.com/oracle-quickstart/oci-hpc-images

To make your life easier, here are a few images build using this website. In the custom image page, import those images by selecting import from URL, select OCI type, choose the correct OS and update the name. Keeping the name of the image the same as the name of the file in the URL lets you keep track of which image is in your tenancy. 

### Ubuntu 22.04

#### HPC (No NVIDIA drivers)

[Canonical-Ubuntu-22.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-22.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-2026.07.16-0.oci)

#### AMD (MI300X, MI355X CX-7)

[Canonical-Ubuntu-22.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-22.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0.oci)

#### AMD (MI355X with Pollara NICs)

[Canonical-Ubuntu-22.04-Kernel-5.15-OFED-5.9-AMD-ROCM-702_POLLARA-OPENMPI-4.1.6](https://objectstorage.us-saltlake-2.oraclecloud.com/p/02QYYf_pFsZlBzMQi5-kp3jTYTJiX4RnkOfgpqTxlvwpO7pCie2bfYrRCr5KD_ll/n/hpctraininglab/b/Sudhir-test-bucket/o/Canonical-Ubuntu-22.04-Kernel-5.15-OFED-5.9-AMD-ROCM-702_POLLARA-OPENMPI-4.1.6)

#### NVIDIA x86 (A100, H100, H200, B200, B300)

[Canonical-Ubuntu-22.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-22.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)

#### NVIDIA Arm (GB200, GB300)

[Canonical-Ubuntu-22.04-aarch64-2026.02.28-0-KERNEL-NVIDIA-64K-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-22.04-aarch64-2026.02.28-0-KERNEL-NVIDIA-64K-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)


### Ubuntu 24.04

#### AMD (MI300X, MI355X CX-7):

[Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0.oci)
[Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.14-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.14-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0.oci)
#### AMD (MI355X with Pollara NICs)

[Canonical-Ubuntu-24.04-2026.02.28-0-MOFED-2410_1140-AMD-ROCM-72-2026.03.13-0](https://objectstorage.ap-kulai-1.oraclecloud.com/p/r7NmOiphWU9Pm9G7yBSkGIYRT5EXCjSNL2BYqso7R-s2zYBoTPmdwn3uyJ-pCvGb/n/hpctraininglab/b/Sudhir-Bucket/o/Canonical-Ubuntu-24.04-2026.02.28-0-MOFED-2410_1140-AMD-ROCM-72-2026.03.13-0)

#### Nvidia_x86 (A100, H100, H200, B200, B300,...):

[Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)
[Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.14-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.14-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)
#### Nvidia_arm (GB200, GB300):
[Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-KERNEL-NVIDIA-64K-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-KERNEL-NVIDIA-64K-6.8-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)
[Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-KERNEL-NVIDIA-64K-6.14-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-KERNEL-NVIDIA-64K-6.14-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)

#### HPC (No Nvidia drivers):
[Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Canonical-Ubuntu-24.04-2026.02.28-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.3.0-2026.07.16-0.oci)

### Oracle Linux 8
Oracle Linux 8 is deprecated and will be phased out in a future release. Prefer Oracle Linux 9 for new deployments.
#### AMD
[Oracle-Linux-8.10-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Oracle-Linux-8.10-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0.oci)
#### NVIDIA GPUs
[Oracle-Linux-8.10-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Oracle-Linux-8.10-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)
#### HPC (No Nvidia drivers):
[Oracle-Linux-8.10-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Oracle-Linux-8.10-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-2026.07.16-0.oci)

### Oracle Linux 9
#### AMD
[Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-AMD-ROCM-724-2026.07.16-0.oci)
#### NVIDIA GPUs
[Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-GPU-595-OPEN-CUDA-13.2-2026.07.16-0.oci)
#### HPC (No Nvidia drivers):
[Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-2026.07.16-0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/rr0d4Zw8yIc-Bwwu8cUDPJ6ooh4LQ_SVHPDBFJ5T89j2drv-hmkeMTwVv8DANpvC/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/2026.07.16/Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.3.0-2026.07.16-0.oci)
