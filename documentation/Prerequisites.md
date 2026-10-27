# Prerequisites and Considerations

Review OCI capacity and IAM requirements, select a supported operating system
and image, and validate any custom image before deploying the stack.

## Contents

- [Service limits](#service-limits)
- [IAM Policies for deployment](#iam-policies-for-deployment)
- [IAM Policies for Runtime](#iam-policies-for-runtime)
- [Supported operating systems](#supported-operating-systems)
- [Images](#images)
  - [Importing published image artifacts (recommended)](#importing-published-image-artifacts-recommended)
  - [Build your own images](#build-your-own-images)
  - [Custom-image qualification](#custom-image-qualification)

## Service Limits

> [!IMPORTANT]
> You need a tenancy, region, target compartment, and access to the selected
> availability domain. Confirm limits and capacity for controller, login,
> monitoring, and compute shapes before deployment. HPC and GPU shapes may
> require a limit increase, reservation, or capacity coordination.
>
> Also check limits for boot volumes, VNICs, private IPs, File Storage mount
> targets, Lustre, Functions, Queue, Streaming, Notifications, Object Storage,
> and MySQL when those features are enabled. See OCI's
> [service-limit request guidance](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident-limit.htm).

## IAM Policies for deployment

The identity running Resource Manager or Terraform must be able to create and
manage the resources selected in the stack.

> [!IMPORTANT]
> Create these deployment identity policies before you create or apply the
> stack. The stack deployment cannot create its required resources without
> them.

**Create the IAM policies for the deployment identity and Compute Management
service:**

```text
allow service compute_management to use tag-namespace in tenancy
allow service compute_management to manage compute-management-family in tenancy
allow service compute_management to read app-catalog-listing in tenancy
allow group <group-name> to manage all-resources in compartment <compartment-name>
```

In the last policy statement:

- `<group-name>` is the IAM group that contains the user who deploys the stack.
- `<compartment-name>` is the compartment where the stack resources are
  deployed.
- `manage all-resources` grants the group permission to create, update, and
  delete all supported resource types in the specified compartment. This
  permission is convenient but broad. Production deployments should use
  dedicated groups, a dedicated compartment, and policies limited to the
  required resource families.

## IAM Policies for Runtime

The stack runtime uses [Resource Principals](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm) for the Function and [Instance Principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm) for cluster nodes.

### Stack-managed IAM (recommended)

Stack-managed IAM automatically creates the runtime dynamic group and the
policies required by enabled features.

To preserve existing IAM configurations, it is disabled by default. Enable it
when you want the stack to create these resources.

To enable stack-managed IAM, choose the option that matches your deployment
method:

- **Resource Manager:** In the **Configure Variables** step, within the
  **Identity** section, enable **Create Policies**.
- **Terraform CLI:** Set `create_policies = true`.

When enabled, the stack creates the required policies and dynamic group for:

- Functions and Queue.
- Cluster resize operations and boot-volume replacement.
- Enabled monitoring, Lustre, and GPU memory-shape features.

### Manually created runtime IAM

> [!TIP]
> Use manual runtime IAM when **Create Policies** is disabled or when your
> organization manages IAM outside the stack.

<details>
<summary>Show manually created IAM policy details</summary>

The deployment policies above are required to create and update the
stack. Keep dynamic groups and policies aligned with the cluster's enabled
features and compartments.

#### Policies for Functions

The Function needs a [dynamic group](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/To_create_a_dynamic_group.htm) and permission to manage resources in the cluster compartment.

##### Create a dynamic group for the Function

```text
ALL {resource.type = 'fnfunc', resource.compartment.id = '<compartment-ocid>'}
```

##### Grant the dynamic group access to the cluster compartment

```text
Allow dynamic-group <function-dynamic-group> to manage all-resources in compartment <compartment-name>
```

Replace `<compartment-ocid>`, `<function-dynamic-group>`, and
`<compartment-name>` with the values for the deployment.

#### Policies for Queue

Management and compute nodes use [Instance Principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm) to read and manage OCI Queue messages.

##### Create a dynamic group for the cluster nodes

```text
All {instance.compartment.id = '<compartment-ocid>'}
```

##### Grant the dynamic group access to Queue

```text
Allow dynamic-group <node-dynamic-group> to use queue-push in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to use queue-pull in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to manage queues in compartment <compartment-name>
```

Replace `<node-dynamic-group>` with the name you choose for the dynamic group
that contains the cluster's management and compute nodes.

If the dynamic group is created in a different identity domain, use
`<identity-domain>/<dynamic-group>` in policy statements.

#### Policies for resizing or adding clusters

When nodes use Instance Principals for authentication, their dynamic group needs
permissions to resize the cluster or add clusters.

##### Create a dynamic group for the cluster nodes

```text
All {instance.compartment.id = '<compartment-ocid>'}
```

##### Grant the baseline resize permissions

```text
Allow dynamic-group <node-dynamic-group> to read app-catalog-listing in tenancy
Allow dynamic-group <node-dynamic-group> to use tag-namespace in tenancy
```

##### Grant the required resource-family permissions

```text
Allow dynamic-group <node-dynamic-group> to manage compute-management-family in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to manage instance-family in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to use virtual-network-family in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to manage volume-family in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to manage dns in compartment <compartment-name>
```

##### Or grant broad compartment access

```text
Allow dynamic-group <node-dynamic-group> to manage all-resources in compartment <compartment-name>
```

Use broad access only when it is appropriate for the organization's IAM model.

#### Policies for Host API

Capacity Topology is created in the root compartment by default. Cluster nodes
need permission to access it.

##### Grant the node dynamic group access to bare-metal hosts

```text
Allow dynamic-group <node-dynamic-group> to manage compute-bare-metal-hosts in tenancy
```

##### Grant GPU-memory fabric access for GB-series GPU shapes

```text
Allow any-user to use compute-hpc-islands in tenancy
Allow any-user to use compute-network-blocks in tenancy
Allow any-user to use compute-local-blocks in tenancy
Allow any-user to use compute-bare-metal-hosts in tenancy
Allow any-user to use compute-gpu-memory-fabrics in tenancy
```

#### Policies for OCI Lustre Filesystem

The OCI Lustre service needs network authorization when the stack creates an
OCI Lustre filesystem.

##### Grant the Lustre service access to virtual networking

```text
Allow service lustrefs to use virtual-network-family in tenancy
```

#### Policies for monitoring

OCI monitoring integration is optional. Enable it with either of these
variables:

- `alerting = true` to push Grafana alerts to OCI topics.
- `ingest_oci_metrics = true` to ingest OCI infrastructure metrics into
  Prometheus through OCI Service Connector Hub, Streaming, and Telegraf.

##### Grant the node dynamic group access to the cluster compartment

```text
Allow dynamic-group <node-dynamic-group> to manage all-resources in compartment <compartment-name>
```

##### Grant the monitoring and Service Connector policies

```text
Allow dynamic-group <node-dynamic-group> to use ons-family in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to use stream-family in compartment <compartment-name>
Allow dynamic-group <node-dynamic-group> to read all-resources in compartment <compartment-name>
```

When `ingest_oci_metrics = true`, both of the following Service Connector Hub policies are required in addition to the dynamic-group policy above:

```
Allow any-user to read metrics in tenancy where all {request.principal.type = 'serviceconnector', request.principal.compartment.id = '<compartment-ocid>'}
Allow any-user to use stream-push in compartment id <target-stream-compartment-ocid> where all {request.principal.type='serviceconnector', request.principal.compartment.id='<compartment-ocid>'}
```

</details>

## Supported operating systems

This stack supports the operating systems and operating system combinations listed below. We can't guarantee any other combination. Mixing Ubuntu with Oracle Linux is not supported.

| Management nodes | Compute nodes | Notes |
|---|---|---|
| Oracle Linux 8 | Oracle Linux 8 | Deprecated and planned for removal in a future release. New deployments should prefer Oracle Linux 9, Ubuntu 22.04, or Ubuntu 24.04. |
| Oracle Linux 9 | Oracle Linux 9 | Preferred |
| Ubuntu 22.04 | Ubuntu 22.04 | Preferred |
| Ubuntu 24.04 | Ubuntu 24.04 | Preferred |

During deployment, set the username in Oracle Resource Manager to `opc` for
Oracle Linux or `ubuntu` for Ubuntu, for both management and compute nodes.

> [!NOTE]
> Use the same operating-system username for SSH access: `opc` for Oracle
> Linux and `ubuntu` for Ubuntu.

## Images
HPC and GPU compute nodes require an image with a compatible kernel, OCI
agents, RDMA stack, accelerator drivers, firmware tooling, and user account.
Successful instance launch alone does not establish image compatibility.

Do not mix operating-system families or versions between management and compute
nodes. Ubuntu deployments use `ubuntu`; Oracle Linux deployments use `opc`.

### Importing published image artifacts (recommended)

This section provides images built with the drivers and tools required for the
corresponding OCI compute shapes.

> [!WARNING]
> Published image URLs are often pre-authenticated Object Storage requests and
> can expire. Verify availability, provenance, checksum, architecture, and
> driver compatibility before importing an artifact into a tenancy.

Select Import from an Object Storage URL, choose the operating system (e.g. Oracle Linux or
Canonical Ubuntu) and OCI as the image type, and retain the artifact filename in the 
custom-image name for traceability.

> [!TIP]
> Import the image and wait for it to become available before deploying the
> stack. For detailed instructions, see [Importing an Image from a
> URL](https://docs.oracle.com/en-us/iaas/private-cloud-appliance/cmn/images/importing-an-image-from-a-url.htm).

#### NVIDIA x86 GPU shapes

<details>
<summary>Show image artifacts</summary>

**Supported shapes:** A100, H100, H200, B200, and B300 families.

##### Ubuntu 24.04

- [Kernel 6.8, GPU driver 580.178.04 LTS, CUDA 13.2, and DOCA-OFED 3.2.3](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-2026.09.18-0-6.8-DOCA-OFED-3.2.3-GPU-580.178.04-OPEN-CUDA-13.2-LTS-2026.10.19-0.oci)
- [Kernel 6.8, GPU driver 595, CUDA 13.2, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-2026.09.18-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.5.0-GPU-595-OPEN-CUDA-13.2-2026.10.19-0.oci)
- [Kernel 6.17, GPU driver 595, CUDA 13.2, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-2026.09.18-0-KERNEL-ORACLE-6.17-DOCA-OFED-3.5.0-GPU-595-OPEN-CUDA-13.2-2026.10.19-0.oci)

##### Ubuntu 22.04

- [Kernel 6.8, GPU driver 580.178.04 LTS, CUDA 13.2, and DOCA-OFED 3.2.3](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-2026.09.18-0-6.8-DOCA-OFED-3.2.3-GPU-580.178.04-OPEN-CUDA-13.2-LTS-2026.10.19-0.oci)
- [Kernel 6.8, GPU driver 595, CUDA 13.2, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-2026.09.18-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.5.0-GPU-595-OPEN-CUDA-13.2-2026.10.19-0.oci)

##### Oracle Linux 9

- [GPU driver 595, CUDA 13.2, RHCK, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.5.0-GPU-595-OPEN-CUDA-13.2-2026.10.19-0.oci)

##### Oracle Linux 8

Oracle Linux 8 is deprecated for new deployments.

- [GPU driver 595, CUDA 13.2, RHCK, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Oracle-Linux-8.10-2026.09.18-0-KERNEL-RHCK-DOCA-OFED-3.5.0-GPU-595-OPEN-CUDA-13.2-2026.10.19-0.oci)

</details>

#### NVIDIA Grace Blackwell GPU shapes

<details>
<summary>Show image artifacts</summary>

**Supported shapes:** GB200 and GB300 families.

##### Ubuntu 24.04

- [Kernel 6.8, GPU driver 580.178.04 LTS, CUDA 13.2, Arm64, and DOCA-OFED 3.2.3](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-aarch64-2026.09.18-0-KERNEL-NVIDIA-64K-6.8-DOCA-OFED-3.2.3-GPU-580.178.04-OPEN-CUDA-13.2-LTS-2026.10.19-0.oci)
- [Kernel 6.17, GPU driver 595, CUDA 13.2, Arm64, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-aarch64-2026.09.18-0-KERNEL-NVIDIA-64K-6.17-DOCA-OFED-3.5.0-GPU-595-OPEN-CUDA-13.2-2026.10.19-0.oci)

##### Ubuntu 22.04

- [Kernel 6.8, GPU driver 580.178.04 LTS, CUDA 13.2, Arm64, and DOCA-OFED 3.2.3](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-aarch64-2026.09.18-0-KERNEL-NVIDIA-64K-6.8-DOCA-OFED-3.2.3-GPU-580.178.04-OPEN-CUDA-13.2-LTS-2026.10.19-0.oci)
- [Kernel 6.8, GPU driver 595, CUDA 13.2, Arm64, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-aarch64-2026.09.18-0-KERNEL-NVIDIA-64K-6.8-DOCA-OFED-3.5.0-GPU-595-OPEN-CUDA-13.2-2026.10.19-0.oci)

</details>

#### AMD GPU shapes

<details>
<summary>Show image artifacts</summary>

**Supported shapes:** MI300X and MI355X families.

##### Ubuntu 24.04

- [MI300X/MI355X CX-7: kernel 6.8, ROCm 10.0, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-2026.09.18-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.5.0-AMD-ROCM-10.0-2026.10.19-0.oci)
- [MI300X/MI355X CX-7: kernel 6.17, ROCm 10.0, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-2026.09.18-0-KERNEL-ORACLE-6.17-DOCA-OFED-3.5.0-AMD-ROCM-10.0-2026.10.19-0.oci)

##### Ubuntu 22.04

- [MI300X/MI355X CX-7: kernel 6.8, ROCm 10.0, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-2026.09.18-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.5.0-AMD-ROCM-10.0-2026.10.19-0.oci)
- [MI355X Pollara: kernel 6.8, Pollara 1.117.5-a-56, and ROCm 7.2.4](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-2026.09.18-0-KERNEL-ORACLE-6.8-POLLARA-1.117.5-a-56-AMD-ROCM-7.2.4-2026.10.19-0.oci)
- [MI355X Pollara: kernel 6.8, Pollara 1.117.5-a-77, and ROCm 7.2.4](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-2026.09.18-0-KERNEL-ORACLE-6.8-POLLARA-1.117.5-a-77-AMD-ROCM-7.2.4-2026.10.19-0.oci)

##### Oracle Linux 9

- [ROCm 10.0, RHCK, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.5.0-AMD-ROCM-10.0-2026.10.19-0.oci)

##### Oracle Linux 8

Oracle Linux 8 is deprecated for new deployments.

- [ROCm 7.2.4, RHCK, and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Oracle-Linux-8.10-2026.09.18-0-KERNEL-RHCK-DOCA-OFED-3.5.0-AMD-ROCM-724-2026.10.19-0.oci)

</details>

#### CPU and HPC shapes

<details>
<summary>Show image artifacts</summary>

These images have no NVIDIA drivers and support compatible CPU and HPC shapes.

##### Ubuntu 24.04

- [Kernel 6.8 and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-24.04-2026.09.18-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.5.0-2026.10.19-0.oci)

##### Ubuntu 22.04

- [Kernel 6.8 and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Canonical-Ubuntu-22.04-2026.09.18-0-KERNEL-ORACLE-6.8-DOCA-OFED-3.5.0-2026.10.19-0.oci)

##### Oracle Linux 9

- [RHCK and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Oracle-Linux-9.7-2026.06.15-1-KERNEL-RHCK-DOCA-OFED-3.5.0-2026.10.19-0.oci)

##### Oracle Linux 8

Oracle Linux 8 is deprecated for new deployments.

- [RHCK and DOCA-OFED 3.5.0](https://idxzjcdglx2s.objectstorage.eu-frankfurt-1.oci.customer-oci.com/p/ZPwaXxeidz3BPrdzEQt_9r-CnrWWOUR_DQ7sB60j3-lqq5bXhLL0LF43J-QYGaua/n/idxzjcdglx2s/b/oci-hpc-image-builds/o/images/release/2026.10.19/Oracle-Linux-8.10-2026.09.18-0-KERNEL-RHCK-DOCA-OFED-3.5.0-2026.10.19-0.oci)

</details>

### Build your own images

The maintained [OCI HPC image builder](https://github.com/oracle-quickstart/oci-hpc-images)
contains Packer and Ansible templates for Oracle Linux and Ubuntu HPC images.
Use it to create reproducible images for the required architecture and driver
stack.

### Custom-image qualification

Test a custom image in a small isolated cluster and verify cloud-init, OCI and
RDMA agents, Ansible convergence, networking, storage, Slurm registration,
accelerator visibility, and the applicable multi-node workload tests.
