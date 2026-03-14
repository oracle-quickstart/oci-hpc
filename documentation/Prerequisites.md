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

### Policies for Functions

The Function uses [Resource Principals](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm) to manage different resources in the Compartment. For the Function to work, the user must create a [Dynamic Group](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/To_create_a_dynamic_group.htm) and grant it resource management authorization in this Compartment.

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
Allow dynamic-group instance_principal to use volumes in compartment compartmentName
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

This stack supports several operating systems and operating system combinations listed below. We can't guarantee any other combination. Although, Ubuntu versions or OL versions usually works fine. Mixing Ubuntu with OL is not supported.

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

### Ubuntu 22.04: 
#### HPC (No Nvidia drivers):

[Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-2026.03.13-0)
#### AMD (MI300X, MI355X CX-7):
[Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-AMD-ROCM-643-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-AMD-ROCM-643-2026.03.13-0)
[Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0)

#### AMD (MI355X with Pollara NICs):
[Canonical-Ubuntu-22.04-Kernel-5.15-OFED-5.9-AMD-ROCM-702_POLLARA-OPENMPI-4.1.6](https://objectstorage.us-saltlake-2.oraclecloud.com/p/02QYYf_pFsZlBzMQi5-kp3jTYTJiX4RnkOfgpqTxlvwpO7pCie2bfYrRCr5KD_ll/n/hpctraininglab/b/Sudhir-test-bucket/o/Canonical-Ubuntu-22.04-Kernel-5.15-OFED-5.9-AMD-ROCM-702_POLLARA-OPENMPI-4.1.6)

#### Nvidia_x86 (A100, H100, H200, B200, B300):
[Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0)
[Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-22.04-2026.02.28-0-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0)
#### Nvidia_arm (GB200, GB300):
[Canonical-Ubuntu-22.04-aarch64-2026.02.28-0-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-22.04-aarch64-2026.02.28-0-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0)


### Ubuntu 24.04: 
Use the Lustre 6.8 kernel images to get the Lustre client.
#### AMD (MI300X, MI355X CX-7):

[Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-AMD-ROCM-643-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-AMD-ROCM-643-2026.03.13-0)
[Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0)
[Canonical-Ubuntu-24.04-2026.02.28-0-6.14-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-2026.02.28-0-6.14-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0)
#### AMD (MI355X with Pollara NICs):
[Canonical-Ubuntu-24.04-2026.02.28-0-MOFED-2410_1140-AMD-ROCM-72-2026.03.13-0](https://objectstorage.ap-kulai-1.oraclecloud.com/p/r7NmOiphWU9Pm9G7yBSkGIYRT5EXCjSNL2BYqso7R-s2zYBoTPmdwn3uyJ-pCvGb/n/hpctraininglab/b/Sudhir-Bucket/o/Canonical-Ubuntu-24.04-2026.02.28-0-MOFED-2410_1140-AMD-ROCM-72-2026.03.13-0)
#### Nvidia_x86 (A100, H100, H200, B200, B300,...):

[Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0)
[Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0)

[Canonical-Ubuntu-24.04-2026.02.28-0-6.14-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-2026.02.28-0-6.14-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0)
#### Nvidia_arm (GB200, GB300):
[Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-6.17-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-6.17-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0)
[Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-6.8-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-aarch64-2026.02.28-0-6.8-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0)

#### HPC (No Nvidia drivers):
[Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Canonical-Ubuntu-24.04-2026.02.28-0-6.8-DOCA-OFED-3.2.1-2026.03.13-0)

### Oracle Linux 8
#### AMD
[Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0)
#### NVIDIA GPUs
[Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0)
[Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0)
#### HPC (No Nvidia drivers):
[Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-8.10-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-2026.03.13-0)

### Oracle Linux 8
#### AMD
[Oracle-Linux-9.6-2025.11.20-0-RHCK-DOCA-OFED-3.2.1-AMD-ROCM-643-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-9.6-2025.11.20-0-RHCK-DOCA-OFED-3.2.1-AMD-ROCM-643-2026.03.13-0)
[Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-AMD-ROCM-72-2026.03.13-0)
#### NVIDIA GPUs
[Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-580-OPEN-CUDA-13.0-2026.03.13-0)
[Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-GPU-590-OPEN-CUDA-13.1-2026.03.13-0)
#### HPC (No Nvidia drivers):
[Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-2026.03.13-0](https://objectstorage.ca-montreal-1.oraclecloud.com/p/AIo4CP0P_DlUelDlsWgGPWmY6FcBQzJWmmFyGKdY0epkh87a9Q3ndvFYycjIxTQ9/n/idxzjcdglx2s/b/images/o/Oracle-Linux-9.7-2026.02.28-0-RHCK-DOCA-OFED-3.2.1-2026.03.13-0)
