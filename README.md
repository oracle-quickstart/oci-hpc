# HPC Cluster Stack

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)

## Table of Content

User can hit the top-right `Outline` button to display the interactive help.

- [HPC Cluster Stack](#hpc-cluster-stack)
  - [Table of Content](#table-of-content)
  - [Introduction](#introduction)
  - [Prerequisites and Consideration](#prerequisites-and-consideration)
    - [Service Limits](#service-limits)
    - [Policies](#policies)
      - [Policies to deploy the stack](#policies-to-deploy-the-stack)
      - [Policies for Functions](#policies-for-functions)
      - [Policies for Queue](#policies-for-queue)
      - [Policies for resizing or adding clusters](#policies-for-resizing-or-adding-clusters)
      - [Policies for Host API](#policies-for-host-api)
    - [Supported operating systems](#supported-operating-systems)
    - [Serverless Part](#serverless-part)
    - [Workflow](#workflow)
      - [Serverless function](#serverless-function)
      - [Node configuration](#node-configuration)
      - [Controller service and actions for configuration](#controller-service-and-actions-for-configuration)
  - [Stack Configuration](#stack-configuration)
    - [Cluster Configuration](#cluster-configuration)
      - [SSH Keys](#ssh-keys)
      - [LDAP](#ldap)
    - [Functions and Events Configuration](#functions-and-events-configuration)
      - [Use an existing OCI Registry](#use-an-existing-oci-registry)
    - [Controller Node Options](#controller-node-options)
    - [Management Nodes Image Options](#management-nodes-image-options)
    - [Compute Nodes Options](#compute-nodes-options)
    - [Login Node Options](#login-node-options)
    - [Cluster Monitoring](#cluster-monitoring)
    - [Storage Options](#storage-options)
      - [Lustre Filesystem](#lustre-filesystem)
      - [File Storage Service](#file-storage-service)
      - [Local Storage (NVMe)](#local-storage-nvme)
      - [General](#general)
        - [Shared home folder](#shared-home-folder)
    - [Network Options](#network-options)
      - [Using an existing VCN](#using-an-existing-vcn)
      - [Private deployment](#private-deployment)
    - [Software](#software)
      - [Create a slurm backup controller](#create-a-slurm-backup-controller)
    - [Debug](#debug)
  - [Stack Usage](#stack-usage)
    - [Resizing and autoscaling](#resizing-and-autoscaling)
    - [Resizing](#resizing)
      - [Resizing with resize.sh](#resizing-with-resizesh)
      - [Resizing with mgmt](#resizing-with-mgmt)
        - [Adding nodes](#adding-nodes)
        - [Removing nodes](#removing-nodes)
        - [Reconfiguring nodes](#reconfiguring-nodes)
    - [Autoscaling](#autoscaling)
      - [Clusters and queues configuration](#clusters-and-queues-configuration)
        - [Specifying node type and queue](#specifying-node-type-and-queue)
        - [Permanent clusters](#permanent-clusters)
        - [Autoscaling activation](#autoscaling-activation)
        - [Clusters folders](#clusters-folders)
    - [Submiting jobs](#submiting-jobs)
    - [Manual Cluster Management](#manual-cluster-management)
      - [Cluster Creation](#cluster-creation)
      - [Cluster Deletion](#cluster-deletion)
    - [Logs](#logs)
  - [Troubleshooting](#troubleshooting)
    - [Where are my logs?](#where-are-my-logs)
      - [slurm (jobs) logs](#slurm-jobs-logs)
      - [cluster logs](#cluster-logs)
    - [How do I reconfigure my stack?](#how-do-i-reconfigure-my-stack)
    - [Healthchecks](#healthchecks)
      - [In-node healthcheck](#in-node-healthcheck)
      - [Monitoring](#monitoring)
  - [Useful Information](#useful-information)
    - [Cloud Services Used](#cloud-services-used)
    - [Collect RDMA NIC Metrics and Upload to Object Storage](#collect-rdma-nic-metrics-and-upload-to-object-storage)
    - [Meshpinger](#meshpinger)
    - [Notes on Nvidia GB200 Deployments](#notes-on-nvidia-gb200-deployments)
    - [Blogs](#blogs)


## Introduction

This Terraform stack deploys a high-performance computing cluster with compute nodes, either CPU or GPU, and management nodes residing in a [Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) (VCN).
It makes use of different OCI services described in the section [cloud services used](#cloud-services-used).
Different storage solutions can also be added.
It is configured and deployed using the [Oracle Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm) managed service.

The following diagram shows the target architecture:

![Target architecture deployed via this Terraform stack.](/images/architecture_diagram.png)

## Prerequisites and Consideration

### Service Limits

> [!WARNING]
> Be sure to have the appropriate Limits for each service that is used. In case you reach *limit exceeded*, you can create a [Service Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident-limit.htm).

### Policies

Different sets of Policies must be set to create the required authorizations.

#### Policies to deploy the stack

**Existing FSS in an existing VCN**
When using an existing VCN, it is possible to point to an existing NFS/FSS instead of creating one. If so, the name of the cluster should not be random and `Use custom cluster name` must be enabled to set `Name of the cluster`. In case of an existing FSS, a record of type A with the mount target IP address as RDATA should be added to the newly created private zone prior to the stack deployment and respect the following syntax:
```
fss-<cluster_name>-controller.<cluster_name>.local
```
`Existing NFS server IP` should be set to `fss-<cluster_name>-controller.<cluster_name>.local`

Finally, a reserved export path called `/config` should be created (`File storage > File System > Your File system > Create Export`)

## Policies
### Policies to deploy the stack: 
```
allow service compute_management to use tag-namespace in tenancy
allow service compute_management to manage compute-management-family in tenancy
allow service compute_management to read app-catalog-listing in tenancy
allow group user to manage all-resources in compartment compartmentName
```

#### Policies for Functions

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

#### Policies for Queue

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

#### Policies for resizing or adding clusters

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

#### Policies for Host API

The Capacity Topology is created by default in the root Compartment. The folowing Policy must be created to access it: 
```
Allow dynamic-group instance_principal to manage compute-bare-metal-hosts in tenancy
```

### Supported operating systems

This stack supports several operating systems and operating system combinations listed below. We can't guarantee any other combination.

|  Management nodes  |   Compute nodes   |
|--------------------|-------------------|
|         OL8        |         OL8       |
|         OL9        |         OL9       |
|    Ubuntu  22.04   |    Ubuntu 22.04   |
|    Ubuntu  24.04   |    Ubuntu 24.04   |

When switching to Ubuntu, user must ensure that the username is changed from `opc` to `ubuntu` in Oracle Resource Manager for both the management nodes and the compute nodes. 

### Serverless Part

This implementation uses [Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm) and [Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm) to communicate the status of the nodes to a [Queue](https://docs.oracle.com/en-us/iaas/Content/queue/overview.htm). The creation of the function requires an [Auth Token](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrygettingauthtoken.htm) to authenticate to the [Oracle Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm) where the function image is stored. Auth Tokens are limited and an existing one can be specified during the configuration.

> [!WARNING]
> By default, a user is limited are limited to 2 Auth Tokens. It is recommended to use an existing Auth Token that can be created in your home region prior to the stack deployment. In case you do not select *"Use existing auth token"*, a Auth Token will be created.
> Please note that after the creation, some time (up to 5 minutes) is needed for the Auth Token to be valid to authenticate with `docker login`. This is why a `time_sleep` resource is executed in Terraform.

### Workflow

![Workflow for node configuration](/images/workflow.png)

#### Serverless function

When nodes are added or removed, an Event triggers an OCI Function. This serverless function will register nodes in the DNS and change their OCI display name to the slurm name if `Change hostname` is set to `true` in the configuration. The current approach is using the Oracle DNS service instead of the `/etc/hosts` file.

When a node is created:
  * Sends a message to the Queue with the IP of the node and status `Starting`
  * Adds DNS entry (hostname_convention must be a tag)
  * Changes the OCI display name to the slurm name (if option checked)

When a node is deleted:
  * Sends a message to the Queue with the IP of the node and status `Terminating`
  * Removes DNS entry 

#### Node configuration

Each compute node will run an Ansible script locally. The nodes will be tagged with the name of the controller node they belong to. That node will mount a network filesystem `/config` folder to store the Ansible playbooks and the keys. The Ansible playbook will run all the tasks that can be run on the host including a task that creates a HTTP server boradcasting node information on port 9876.

Example of the information:
```
ip_address: '172.16.0.66',
AD: 'xXXX:CA-TORONTO-1-AD-1',
cluster_name: 'loving-flounder',
compartment: 'ocid1.compartment.oc1..xxxxxxxxxxxxxxxxx',
controller_name: 'loving-flounder-controller',
fss_mount: 'None',
hostname: 'loving-flounder-controller',
hpc_island: 'None',
networkBlockId: 'None',
oci_name: 'loving-flounder-controller',
ocid: 'ocid1.instance.oc1.ca-toronto-1.xxxxxxxxxxxxxxxxxxxxxxxx',
rackID: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
railId: 'None',
role: 'controller',
serial: 'Not Specified',
shape: 'VM.Standard.E4.Flex',
status: 'configured',
```

#### Controller service and actions for configuration

The controller node:
* runs a service that reads messages in the Queue and stores the information in the MySQL database,
* queries informations of sent by the webservers on each of the compute nodes and store these in the MySQL database,
* runs Ansible roles locally when the nodes are marked as `Ready` in order to finalise the cluster setup:
  * Runs the `Fix_ldap` role
  * Adds/removes the node to `prometheus.yml`
  * Adds/removes the node in the slurm configuration, i.e. `topology.conf` and `gres.conf`

## Notes on Deployments for Memory Fabric Based Shapes, such as Nvidia GB200 / GB300
When deploying this shape you should configure and deploy the stack as usual EXCEPT that the initial size of the cluster should to be set to 0, but otherwise fully define the instance configuration for the compute hosts in the stack deployment.  Once you log into the cluster controller you can create the initial GPU Memory Cluster like this.


Now use the OCID from above for --fabric, as well as the number of AVAILABLE hosts for --count:
```
mgmt clusters create --count 16 --cluster my_cluster --instancetype default --fabric ocid1.computegpumemoryfabric.oc1..... 
```

## Stack Configuration

Use the above command to add ONLY THE FIRST SET OF INSTANCES.  See below on how to add additional gpumemoryfabrics to the compute cluster named my_cluster that was created above (otherwise inter-rack communication will not work).

### Cluster Configuration

To add hosts from other computegpumemoryfabrics to the cluster:
```
mgmt clusters add memory-fabric --count 18 --cluster my_cluster --instancetype default --fabric ocid1.computegpumemoryfabric.oc1.... 
```

User must provide a public ssh key to allow ssh connection to the management nodes (controller, controller backup, login and monitoring).

#### LDAP

If the LDAP option is selected during the stack configuration, the controller node will act as an LDAP server for the cluster. In this case, it is strongly recommended to leave the default value for the shared home directory. User management can be performed from the controller using the `cluster` command. 

Example:
* Adding a new user: 
```cluster user add name```
By default, a `privilege` group that has access to the NFS and can have sudo access on all nodes (defined at the stack creation step) is created with the ID 9876.
* The group name can be modified:
```cluster user add name --gid 9876```
* To avoid generating a user-specific key for passwordless ssh between nodes, use the `--nossh` option: 
```cluster user add name --nossh --gid 9876```

### Functions and Events Configuration

#### Use an existing OCI Registry

Select this option to use existing Function container registry.

### Controller Node Options

In this section, define controller node Availability Domain, shape, cores and memory (for Flex virtual machines) and size of the boot volume. The image is defined in the next section.

### Management Nodes Image Options

There are possibly up to 4 management nodes:
* Controller (required) : for cluster admin tasks (node management, user management, cluster resizing, etc.)
* Login: for users tasks (job submission, data management)
* Monitoring: monitoring tasks dedicated node (Prometheus, Grafana)
* Controller backup: for High Availability purpose (requires the File Storage Service to host a slurm MySQL HeatWave database)

Marketplace images are based on Oracle Linux 8. They are HPC specific versions with NVIDIA or AMD GPU drivers (except HPC_OL8) and RDMA drivers preinstalled.

Other images such as Ubuntu or CentOS can be used. Username must be changed accordingly (default is `opc` for OL8, `ubuntu` for Ubuntu).

If a non-listed image must be used, the image ocid must be provided. The image must have been previously imported as a Custom Image.

### Compute Nodes Options

For the compute nodes, first define the Availability Domain and the node shape. If RoCE V2 cluster network is enabled, only Bare Metal shapes that support RDMA are available. If not, any shape, VM or BM, can be used as compute nodes.

The initial cluster size corresponds to the number of nodes of the permanent cluster.

Boot volume size can be set at this stage.

Image options are the same as for the management nodes. Management node and compute node images do not have to be identical but they must be compatible. Example: Canonical-Ubuntu-22.04 for the management nodes and Canonical-Ubuntu-22.04-OFED-GPU-570-OPEN-CUDA-12.8 for the compute nodes (GPU Bare Metal).

### Login Node Options

In this section, define login node Availability Domain, shape, cores and memory (for Flex virtual machines) and size of the boot volume. Image is defined in the [Management Nodes Image Options section](#management-nodes-image-options).

### Cluster Monitoring

HPC cluster monitoring tools can be installed. This includes alerting tools, and a monitoring node to host the tools with the same options as the controller and the login nodes.

### Storage Options

Depending on the requirements, different "hot" storage options can be configured:
* OCI File Storage service
* OCI File Storage with Lustre service
* Local Storage (NVMe)

#### Lustre Filesystem

The OCI File Storage with Lustre is a fully managed service that delivers the performance ans scale benefits of Lustre, including:
* Milliseconds of meta-data latency
* Capacity to petabytes
* High throughput of terabytes per second
while eliminating the complexity of management.

Capacity is a multiple of 31.2 TB. Performance tier must be selected form 125, 250, 500 or 1000 MBps per provisioned TB.

#### File Storage Service

The OCI File Storage managed service is a highly available network file system (NFS) that enables multiple servers to access data. It is elastic up to 8 exabytes with asynchronous replication, snapshot and clone capabilities.

The cluster can connect to an exising File Storage service or create a new one.
For an `existing` one, simply provide the required information (address, mounting path, credentials).
For a `new` one, specify the number of mount targets. Mount target performance is 1 Gbps per default but can be upgraded to 20, 40 or 80 Gbps with High Performance Mount Targets (HPMT). HPMT-20, -40 and -80 respectively include 20, 40 and 80 TB of storage capacity.

Other options include the NFS mounting path, the NFS server path, Compartment and Availability Domain.

#### Local Storage (NVMe)

Compute bare metal nodes feature one or more NVMe local disks.
The `Mount localdisk` option automatically mount all the disks on all the nodes (compute nodes and management nodes if applicable).
The `One Logical Volume` unifies all the disks to create one local storage point (RAID 0).
The `Redundancy` sets the disks configuration to RAID 1.

> [!WARNING]
> Local storage can be subject to hardware failure and does not benefit from any built-in replication, cloning or snapshot capabilities. Therefore, this storage solution must not be used for any valuable data. Prefer File Storage or File Storage with Lustre instead.

#### General

##### Shared home folder

By default, the `home` folder is located on the NFS shared between all nodes from the controller node. User has the possibility to use a Filesystem Service (FSS) to share the home directory as well to keep working if the controller node goes down.
User can either create a new FSS (be aware that it will be destroyed with the stack) or use an existing one (Mount Target, path, etc. will be required). If an existing FSS is used, /home should not be used as a mount point. The stack will take care of creating a `$nfsshare/home` directory and mounting it at `/home` after copying all the appropriate files. 

### Network Options

#### Using an existing VCN

This implementation uses Private DNS view. When using an existing VCN, make sure you have a Private Zone with `<cluster-name>.local`. You also must create the correct DCHP Options set to `Internet and VCN Resolver`, `Custom Search Domain` with the search domain corresponding to `<cluster-name>.local`. Finally, the DHCP Options of the different subnets must be set to the newly created DCHP Options and not "Default DHCP Options..."

> [!WARNING]
> If the DHCP Options and the Private Zone are not set properly, the deployment will fail. Make sure they exist or do not use an existing VCN and deploy a new one with this stack.

#### Private deployment

If `true`, this will create a private endpoint in order for Oracle Resource Manager to create the management nodes (controller, backup controller, login and monitoring) and the future nodes in private subnet(s). 
* If "Use Existing Network" is `false`, Terraform will create two private subnets, one for the management nodes and one for the compute nodes.  
* If "Use Existing Network" is `true`, the user must indicate a private subnet for the management nodes. For the compute nodes, they can reside either in the same private subent as the management nodes or in another one. 

> [!IMPORTANT]
> The management nodes will reside in a private subnet. Therefore, the creation of a [bastion service](https://docs.public.content.oci.oraclecloud.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm), a VPN or a FastConnect connection is required. If a public subnet exists in the VCN, adapting the security lists and creating a jump host also works. Finally, a peering connection can also be established between the private subnet and another VCN that is reachable by the user.

### Software

#### Create a slurm backup controller

> [!IMPORTANT]
> A FSS must be used to have a shared directory for the state.

If checked, a managed MySQL database is created via [MySQL Heatwave](https://docs.oracle.com/en-us/iaas/mysql-database/home.htm). 
In the slurm configuration, the controller and its backup each have the following slurm services running:
* the `slurmctld` service (with [SlurmctldHost](https://slurm.schedmd.com/slurm.conf.html#OPT_SlurmctldHost) defined twice as controller and backup, [AccountingStorageHost](https://slurm.schedmd.com/slurm.conf.html#OPT_AccountingStorageHost) pointing to the controller and [AccountingStorageBackupHost](https://slurm.schedmd.com/slurm.conf.html#OPT_AccountingStorageBackupHost) pointing to the backup in `slurm.conf`),
* the `slurmdbd` service (with [DbdHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_DbdHost) pointing to the controller, [DbdBackupHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_DbdBackupHost) pointing to the backup and [StorageHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_StorageHost) pointing to the database in `slurmdbd.conf`).

Both the controller and its backup can query the database if one of them is down.

### Debug

## Stack Usage

### Resizing and autoscaling

* Autoscaling creates a cluster when a job in the slurm queue does not have the required infrastructure and destroys it when the job is finished (after a surviving period of time) if no other job in the slurm queue can use it.
* Resizing modifies the size (the number of nodes) of a cluster.

In some cases, increasing the number of nodes of an existing cluster instead of creating a new one next to it may be seen as a better idea. Because Oracle Cloud RDMA is non-virtualized, nodes are organized in a *node < rack < island < network block < data center* pattern. This provides low latency and high throuput for node communication but it may lead to capacity errors if additional nodes cannot be found in the same network block as the initial cluster. So while there may be capacity available in the Availability Domain (data center), user may not be able to grow its current RDMA cluster. By creating as many *small* RDMA clusters as jobs (potentially in different network blocks), autoscaling mitigates the *out-of-capacity* risk compared to resizing a single *large* RDMA cluster (for which all nodes must reside in the same network block).

### Resizing

#### Resizing with resize.sh

> [!NOTE]
> This section might need some improvements. It is now possible to resize directly from the OCI web console thanks to the event/function/queue approach.

Cluster resizing refers to ability to add or remove nodes from an existing cluster network. Apart from add/remove, the `mgmt` command can also be used to reconfigure the nodes. 

Resizing a HPC cluster with Cluster Network consists in 2 major sub-steps:
1. Adding or removing compute node(s) (IaaS provisioning) to the cluster using the OCI Python SDK,
2. Configuring the new compute node(s) using Ansible:
  -  Configures newly added compute nodes to be ready to run slurm jobs,
  -  Reconfigures services such as slurm to discover and add the new compute nodes on all nodes.

#### Resizing with mgmt

> [!IMPORTANT]
> If you are using GB200 or GB300 hosts, see special notes above

The `mgmt` tool is deployed on the controller node as part of the HPC Cluster Stack deployment. The full mgmt command help is available [here](documentation/mgmt-help.txt). 

##### Adding nodes

Examples:

* Adding one node:
```
mgmt clusters add add-node --count 1
```
* Adding three nodes to cluster compute-1-hpc:
```
mgmt clusters add add-node --count 3 --cluster compute-1-hpc
```

##### Removing nodes

Removing nodes from a HPC cluster consists in 2 major sub-steps:
- Removing node(s) (IaaS termination) from the cluster using OCI Python SDK,
- Reconfiguring the remaining nodes in the cluster using Ansible:
  -  Removing reference to removed node(s) on rest of the nodes (update /etc/hosts, slurm configs, etc.).

Examples:

* Removing specific node:  
```
mgmt nodes terminate --nodes GPU-123
```
* Removing a list of nodes (comma separated):  
```
mgmt nodes terminate --nodes GPU-123,GPU-456
```
* Removing a list of nodes (slurm notation):  
```
mgmt nodes terminate --nodes GPU-[123,456]
```

##### Reconfiguring nodes

Reconfiguring nodes of the cluster consists in running specific Ansible tasks on both management and/or compute nodes.

Example:

* Reconfiguring a set of 3 compute nodes (slurm notation):
```
mgmt nodes reconfigure compute --nodes GPU-[1,2,3]
```

### Autoscaling

> [!WARNING]
> Not to be confused with the [Autoscaling service](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/autoscalinginstancepools.htm) from OCI.

The autoscaling works as a “cluster per job” approach. This means that for job waiting in the queue, a new cluster is created specifically for that job. Autoscaling also takes care of spinning down clusters. By default, a cluster is left idle for 10 minutes before shutting it down. Autoscaling is achieved with a cron job to be able to quickly switch from one scheduler to the next one.

Smaller jobs can run on large clusters and the clusters will be resized down after the grace period to only the necessary nodes. Clusters will NOT be scaled out. Instead, a new larger cluster is spun up and the smaller cluster is spun down to avoid capacity issues in the HPC island. 

Initial cluster deployed through the stack is permanent: it will never be spun down.

#### Clusters and queues configuration

A configuration file at `/opt/oci-hpc/conf/queues.conf` and a custom version example at `/opt/oci-hpc/conf/queues.conf.example`are provided to show how multiple queues and multiple instance types can be added. Examples are given for HPC bare metal instances, GPU bare metal instances and Flexible Virtual Machines. 

##### Specifying node type and queue

The instance type name must be used as a feature in the slurm job definition to make sure it runs on the right type of node. 
Only one default instance-type per queue and one default queue can be specified. To submit jobs on a non default queue, user must either add the `#SBATCH --partition compute` line to the `.sbatch` file header or specify the queue in the command line:
```
sbatch -p queuename job.sh
```

##### Permanent clusters

When the keyword `permanent` is set to `true`, clusters of this node type can be created but cannot be deleted until it is set to `false`. It is not needed to reconfigure slurm after you change that value in the queue configuration file. 

After a modification of the `/opt/oci-hpc/conf/queues.conf`, user must run the `/opt/oci-hpc/bin/slurm_config.sh` command to make sure that modifications will be taken into account.

Queues and instances configuration can be put back in the initial state with `/opt/oci-hpc/bin/slurm_config.sh --initial`.

##### Autoscaling activation

To turn on autoscaling:
1. Run `crontab -e` and uncomment the following line:
```
* * * * * /opt/oci-hpc/autoscaling/crontab/autoscale_slurm.sh >> /config/logs/crontab_slurm.log 2>&1
```
2. Set `autoscaling = true` in `/etc/ansible/hosts`.

##### Clusters folders

For each cluster, except the permanent one, a cluster folder is created in:
```
/opt/oci-hpc/autoscaling/clusters/clustername
```

### Submiting jobs

Slurm jobs can be submitted as always but a few more constraints can be set: 

Example (`/opt/oci-hpc/samples/submit/` file):

```
#!/bin/sh
#SBATCH -n 72
#SBATCH --ntasks-per-node 36
#SBATCH --exclusive
#SBATCH --job-name sleep_job
#SBATCH --constraint hpc-default

cd /nfs/scratch
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID
MACHINEFILE="hostfile"

# Generate Machinefile for mpi such that hosts are in the same
# order as if run via srun

scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE
sed -i "s/$/:${SLURM_NTASKS_PER_NODE}/" $MACHINEFILE
cat $MACHINEFILE

# Run using generated Machine file

sleep 1000
```
 
- Instance Type: user can specify the OCI instance type that he’d like the job to run on as a constraint. This will ensure that the job runs on the right shape and/or that the right cluster will be created. Instance types are defined in the `/opt/oci-hpc/conf/queues.conf` file in yml format. For each new instance type, user must keep all of the fields even if they are not applicable. User can define multiple queues and multiple instance types in each queue. If no instance type is specified when creating a job, the default one will be selected.

- `cpu-bind`: on Ubuntu 22.04, the stack uses Cgroup v2. It has been found that the default `cpu-bind` may give some issues when hyperthreading is turned off. If an error similar to `error: task_g_set_affinity: Invalid argument` occurs, user can try running the job with the `--cpu-bind=none` or `--cpu-bind=sockets` options.

### Manual Cluster Management

Clusters can be created and deleted manually (for example when autoscaling is not activated).

#### Cluster Creation

To create a cluster manually, run:
```
/opt/oci-hpc/bin/create_cluster.sh NodeNumber clustername instance_type queue_name
```
Example:
The command:
```
/opt/oci-hpc/bin/create_cluster.sh 4 compute2-1-hpc HPC_instance compute2
```
creates a 4 HPC_instance node cluster named compute2-1-hpc in the compute2 queue.

#### Cluster Deletion

To delete a cluster manually, run:
```
/opt/oci-hpc/bin/delete_cluster.sh clustername
```
If something goes wrong during the deletion process, the deletion can be forced with the `FORCE` option:
```
/opt/oci-hpc/bin/delete_cluster.sh clustername FORCE
```
If the cluster is already being destroyed, there will be a `currently_destroying` file in the cluster folder (`/opt/oci-hpc/autoscaling/clusters/clustername`).

### Logs

The infrastructure logs are stored in:
```
/config/logs
```

Each cluster has its own log file with named `create_clustername_date.log` and `delete_clustername_date.log` for its creation and deletion processes. The logs of the crontab is stored in `crontab_slurm.log`.

## Troubleshooting

The cluster state and activity is logged in different files.

### Where are my logs?

#### slurm (jobs) logs

The slurm job logs are created in the folder from which the job is launched. Its generic name is `slurm-jobid.out`.

#### cluster logs

The cluster logs (creation, resizing, deletion) are stored in the `/config/logs` folder.

### How do I reconfigure my stack?

### Healthchecks

#### In-node healthcheck

```
sudo python3 /opt/oci-hpc/healthchecks/check_gpu_setup.py
```

#### Monitoring

## Useful Information

### Cloud Services Used

This stack uses the following OCI services:

* Compute 
  * [Instance](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm)
  * [Instance Configuration](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/creatinginstanceconfig.htm)
  * [Compute Cluster](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/compute-clusters.htm) (if checked)
  * [Cluster Network](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/managingclusternetworks.htm) (if checked)
* [Networking](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm)
  * [VCN and subnet](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/Overview_of_VCNs_and_Subnets.htm)
  * [Route Tables](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingroutetables.htm)
  * [Security Lists](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securitylists.htm)
  * [Service Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/servicegateway.htm)
  * [NAT Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/NATgateway.htm)
  * [Internet Gateway](https://docs.oracle.com/en-us/iaas/Content/Network/Tasks/managingIGs.htm) (if using a Public Subnet)
  * [Private DNS view](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/privatedns.htm)
* [Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm)
* [Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm)
* [Queue](https://docs.oracle.com/en-us/iaas/Content/queue/overview.htm)  
* [Oracle registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm)
* [Auth Token](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrygettingauthtoken.htm)
* Storage
  * [Block Volume](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/overview.htm)
  * [File System Service](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/filestorageoverview.htm) (if checked)
* [Private Endpoint](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/private-endpoints.htm) (if controller in a private subnet)
* [MySQL Database](https://docs.oracle.com/en-us/iaas/mysql-database/home.htm) (if `Create a back-up Slurm Controller` is checked)

### Collect RDMA NIC Metrics and Upload to Object Storage

OCI-HPC is deployed in customer tenancy. So, OCI service teams cannot access metrics from these OCI-HPC stack clusters. Due to overcome this issue, in release,
we introduce a feature to collect RDMA NIC Metrics and upload those metrics to Object Storage. Later on, that Object Storage URL could be shared with OCI service
teams. After that URL, OCI service teams could access metrics and use those metrics for debugging purpose.

To collect RDMA NIC Metrics and upload those to Object Storage, user needs to follow these following steps:

1. Create a PAR (PreAuthenticated Request) by making sure that the "Create Object Storage PAR" checkbox is ticked (it is by default) at the stack configuration step in the Resource Manager.
2. Use shell script `upload_rdma_nic_metrics.sh` to collect and upload metrics to object storage. User can configure metrics collection limits and intervals using the `rdma_metrics_collection_config.conf` config file.

### Meshpinger

Meshpinger is a tool for validating network layer connectivity between RDMA NICs on a cluster network in OCI. The tool is capable of initiating ICMP ping from every RDMA NIC port on the cluster network to every other RDMA NIC port on the same cluster network and reporting back the success/failure status of the pings performed in the form of logs.

Running the tool before starting workload on a cluster network should serve as a good precheck step to gain confidence on the network reachability between RDMA NICs. Typical causes for reachability failures that the tool can help pinpoint are:
1. Link down on the RDMA NIC
2. RDMA interface initialization or configuration issues including IP address assignment to the interface
3. Insufficient ARP table size on the node to store all needed peer mac addresses

### Notes on Nvidia GB200 Deployments

Currently, the TerraForm connector is not working with GB200 based shapes due to the requirements around GPU memory cluster constructs. When deploying this shape, user must configure and deploy the stack as usual **EXCEPT** that the initial size of the cluster must be set to 0. Otherwise, user fully defines the compute nodes options during the stack configuration. Once logged in to the cluster controller node, user creates the initial `gpumemorycluster` as explained below.

1. Check that the `lifecycle_state` is `AVAILABLE`, the `fabric_health` must be `HEALTHY`, and check `AVAILABLE` nodes:
```
mgmt fabrics list
                                                                        Fabrics
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┓
┃ id                                                                           ┃ lifecycle_state ┃ fabric_health ┃ memory_cluster ┃ OCCUPIED ┃ AVAILABLE ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━┩
│ ocid1.computegpumemoryfabric.oc1....                                         │ AVAILABLE       │ HEALTHY       │ None           │ 0        │ 18        │
└──────────────────────────────────────────────────────────────────────────────┴─────────────────┴───────────────┴────────────────┴──────────┴───────────┘
```
2. Use the OCID from above for `--fabric`, as well as the number of `AVAILABLE` hosts for `--count`:
```
mgmt clusters create --count 16 --cluster gb200 --instancetype default --fabric ocid1.computegpumemoryfabric.oc1..... 
```
This creates a `computegpumemorycluster` with a name `cluster_xxxxx` and spins up the number of instances given in `--count`.  This is reflected in the `mgmt fabrics list` command output after a few minutes. The nodes and their respective informations can be seen with:
```
mgmt nodes list
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ hostname                 ┃ healthcheck_recommendat… ┃ status  ┃ compute_status ┃ cluster_name  ┃ memory_cluster_name ┃ ocid                      ┃ serial        ┃ ip_address    ┃ shape               ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ trusting-dory-controller │                          │ running │ configuring    │ cluster-name  │ None                │ ocid1.instance.oc1.ap-sy… │ Not Specified │ 172.16.xxx.xxx  │ VM.Standard.E5.Flex │
│ GPU-123                 │ Healthy                  │ running │ configuring    │ cluster-name  │ cluster-name_wuuja  │ ocid1.instance.oc1.ap-sy… │ 1234ABCXXX    │ 172.16.xxx.xxx │ BM.GPU.GB200.4      │
│ GPU-456                  │ Healthy                  │ running │ configuring    │ cluster-name  │ cluster-name_wuuja  │ ocid1.instance.oc1.ap-sy… │ 5678DEFYYY    │ 172.16.xxx.xxx │ BM.GPU.GB200.4      │
└──────────────────────────┴──────────────────────────┴─────────┴────────────────┴───────────────┴─────────────────────┴───────────────────────────┴───────────────┴───────────────┴─────────────────────┘
```

> [!WARNING]
> Use the above command **ONLY** to add the first set of instances (see below how to add `gpumemoryfabrics` to the compute cluster named `gb200` that has been created above), otherwise inter-rack communication will not work.

To add more nodes from the same `computegpumemoryfabric` to this cluster, use the corresponding `cluster_xxxxx` name for these nodes as shown as `memory_cluster_name` in `mgmt fabrics list`:
```
mgmt clusters add node --count 2 --memorycluster cluster_xxxxx
```
To add nodes from other `computegpumemoryfabrics` to the cluster:
```
mgmt clusters add memory-fabric --count 18 --cluster gb200 --instancetype default --fabric ocid1.computegpumemoryfabric.oc1.... 
```
To delete a `computegpumemorycluster` and terminate all of the instances:
```
mgmt clusters delete --memory_cluster cluster_xxxxx
```

### Blogs