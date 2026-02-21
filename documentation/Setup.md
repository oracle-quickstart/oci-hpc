# Stack Configuration

## Cluster Configuration

### Public SSH key

User must provide a public ssh key to allow ssh connection to the management nodes (controller, controller backup, login and monitoring).

### Use custom cluster name

When using an existing VCN, it is possible to point to an `existing` NFS/FSS instead of creating a `new` one. If so, the name of the cluster should not be random and `Use custom cluster name` must be enabled to set `Name of the cluster`.

### LDAP

If the LDAP option is selected during the stack configuration, the controller node will act as an LDAP server for the cluster. In this case, it is strongly recommended to leave the default value for the shared home directory. User management can be performed from the controller using the `cluster` command. 

Example:
* Adding a new user: 
```cluster user add name```
By default, a `privilege` group that has access to the NFS and can have sudo access on all nodes (defined at the stack creation step) is created with the ID 9876.
* The group name can be modified:
```cluster user add name --gid 9876```
* To avoid generating a user-specific key for passwordless ssh between nodes, use the `--nossh` option: 
```cluster user add name --nossh --gid 9876```

## Functions and Events Configuration

### Use an existing OCI Registry

Select this option to use existing image container registry.

## Controller Node Options

In this section, define controller node Availability Domain, shape, cores and memory (for Flex virtual machines) and size of the boot volume. The image is defined in the next section.

## Management Nodes Image Options

There are possibly up to 4 management nodes:
* Controller (required) : for cluster admin tasks (node management, user management, cluster resizing, etc.)
* Login: for users tasks (job submission, data management)
* Monitoring: monitoring tasks dedicated node (Prometheus, Grafana)
* Controller backup: for High Availability purpose (requires the File Storage Service to host a slurm MySQL HeatWave database)

Marketplace images are based on Oracle Linux 8. They are HPC specific versions with NVIDIA or AMD GPU drivers (except HPC_OL8) and RDMA drivers preinstalled.

Other images such as Ubuntu or CentOS can be used. Username must be changed accordingly (default is `opc` for OL8, `ubuntu` for Ubuntu).

If a non-listed image must be used, the image ocid must be provided. The image must have been previously imported as a Custom Image.

## Compute Nodes Options

For the compute nodes, first define the Availability Domain and the node shape. If RoCE V2 cluster network is enabled, only Bare Metal shapes that support RDMA are available. If not, any shape, VM or BM, can be used as compute nodes.

### Main (permanent) partition

The initial cluster size corresponds to the number of nodes of the permanent cluster.

Boot volume size can be set at this stage.

Image options are the same as for the management nodes. Management node and compute node images do not have to be identical but they must be compatible. Example: Canonical-Ubuntu-22.04 for the management nodes and Canonical-Ubuntu-22.04-OFED-GPU-570-OPEN-CUDA-12.8 for the compute nodes (GPU Bare Metal).

### On-demand partition

This feature takes advantage of [Slurm Power Saving](https://slurm.schedmd.com/power_save.html) mechanism. One can add an additional "on-demand" partition by checking ```On-Demand Partition```. This will create a new slurm partition with name "ondemand".
To submit a job, specify the correct partition (i.e ```--partition ondemand```). When submitting the job, ```ResumeProgram``` specified in ```slurm.conf``` is triggered to bring the correct number of nodes in Oracle Cloud and register them in Slurm to run the job. Once the job has run and ```SuspendTime```is reached, ```SuspendProgram``` is triggered to unregister the node and terminate it in Oracle Cloud Infrastructure.

> [!WARNING]
> Currently, when defining an on-demand partition, the key ```stand_alone:``` should be ```true```. This is because we are not using [NodeSet](https://slurm.schedmd.com/slurm.conf.html#OPT_NodeSet) but rather [OPT_NodeName](https://slurm.schedmd.com/slurm.conf.html#OPT_NodeName) and the name of the node needs to be known beforehand. This is currenlty not possible with Cluster Networks and Instance Pools.

## Login Node Options

In this section, define login node Availability Domain, shape, cores and memory (for Flex virtual machines) and size of the boot volume. Image is defined in the [Management Nodes Image Options section](#management-nodes-image-options).

## Cluster Monitoring

HPC cluster monitoring tools can be installed. This includes alerting tools, and a monitoring node to host the tools with the same options as the controller and the login nodes.

## Storage Options

Depending on the requirements, different "hot" storage options can be configured:
* OCI File Storage service
* OCI File Storage with Lustre service
* Local Storage (NVMe)

### Lustre Filesystem

The OCI File Storage with Lustre is a fully managed service that delivers the performance ans scale benefits of Lustre, including:
* Milliseconds of meta-data latency
* Capacity to petabytes
* High throughput of terabytes per second
while eliminating the complexity of management.

Capacity is a multiple of 31.2 TB. Performance tier must be selected form 125, 250, 500 or 1000 MBps per provisioned TB.

### File Storage Service

The OCI File Storage managed service is a highly available network file system (NFS) that enables multiple servers to access data. It is elastic up to 8 exabytes with asynchronous replication, snapshot and clone capabilities.

The cluster can connect to an exising File Storage service or create a new one.

For an `existing` FSS, simply provide the required information (address, mounting path, credentials).

> [!WARNING]
> For an existing FSS, a record of type A with the mount target IP address as RDATA should be added to the newly created private zone prior to the stack deployment and respect the following syntax:
```
fss-<cluster_name>-controller.<cluster_name>.local
```
> `Existing NFS server IP` should be set to `fss-<cluster_name>-controller.<cluster_name>.local`.
> Finally, a reserved export path called `/config` should be created (`File storage > File System > Your File system > Create Export`)

For a `new` FSS, specify the number of mount targets. Mount target performance is 1 Gbps per default but can be upgraded to 20, 40 or 80 Gbps with High Performance Mount Targets (HPMT). HPMT-20, -40 and -80 respectively include 20, 40 and 80 TB of storage capacity.

Other options include the NFS mounting path, the NFS server path, Compartment and Availability Domain.

### Local Storage (NVMe)

Compute bare metal nodes feature one or more NVMe local disks.
The `Mount localdisk` option automatically mount all the disks on all the nodes (compute nodes and management nodes if applicable).
The `One Logical Volume` unifies all the disks to create one local storage point (RAID 0).
The `Redundancy` sets the disks configuration to RAID 1.

> [!WARNING]
> Local storage can be subject to hardware failure and does not benefit from any built-in replication, cloning or snapshot capabilities. Therefore, this storage solution must not be used for any valuable data. Prefer File Storage or File Storage with Lustre instead.

### General

#### Shared home folder

By default, the `home` folder is located on the NFS shared between all nodes from the controller node. User has the possibility to use a Filesystem Service (FSS) to share the home directory as well to keep working if the controller node goes down.
User can either create a new FSS (be aware that it will be destroyed with the stack) or use an existing one (Mount Target, path, etc. will be required). If an existing FSS is used, /home should not be used as a mount point. The stack will take care of creating a `$nfsshare/home` directory and mounting it at `/home` after copying all the appropriate files. 

## Network Options

### Using an existing VCN

This implementation uses Private DNS view. When using an existing VCN, make sure you have a Private Zone with `<cluster-name>.local`. You also must create the correct DCHP Options set to `Internet and VCN Resolver`, `Custom Search Domain` with the search domain corresponding to `<cluster-name>.local`. Finally, the DHCP Options of the different subnets must be set to the newly created DCHP Options and not "Default DHCP Options..."

> [!WARNING]
> If the DHCP Options and the Private Zone are not set properly, the deployment will fail. Make sure they exist or do not use an existing VCN and deploy a new one with this stack.

### Private deployment

If `true`, this will create a private endpoint in order for Oracle Resource Manager to create the management nodes (controller, backup controller, login and monitoring) and the future nodes in private subnet(s). 
* If "Use Existing Network" is `false`, Terraform will create two private subnets, one for the management nodes and one for the compute nodes.  
* If "Use Existing Network" is `true`, the user must indicate a private subnet for the management nodes. For the compute nodes, they can reside either in the same private subent as the management nodes or in another one. 

> [!IMPORTANT]
> The management nodes will reside in a private subnet. Therefore, the creation of a [bastion service](https://docs.public.content.oci.oraclecloud.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm), a VPN or a FastConnect connection is required. If a public subnet exists in the VCN, adapting the security lists and creating a jump host also works. Finally, a peering connection can also be established between the private subnet and another VCN that is reachable by the user.

## Software

### Create a slurm backup controller

> [!IMPORTANT]
> A FSS must be used to have a shared directory for the state.

If checked, a managed MySQL database is created via [MySQL Heatwave](https://docs.oracle.com/en-us/iaas/mysql-database/home.htm). 
In the slurm configuration, the controller and its backup each have the following slurm services running:
* the `slurmctld` service (with [SlurmctldHost](https://slurm.schedmd.com/slurm.conf.html#OPT_SlurmctldHost) defined twice as controller and backup, [AccountingStorageHost](https://slurm.schedmd.com/slurm.conf.html#OPT_AccountingStorageHost) pointing to the controller and [AccountingStorageBackupHost](https://slurm.schedmd.com/slurm.conf.html#OPT_AccountingStorageBackupHost) pointing to the backup in `slurm.conf`),
* the `slurmdbd` service (with [DbdHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_DbdHost) pointing to the controller, [DbdBackupHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_DbdBackupHost) pointing to the backup and [StorageHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_StorageHost) pointing to the database in `slurmdbd.conf`).

Both the controller and its backup can query the database if one of them is down.

### Join [Slurm federation](https://slurm.schedmd.com/network.html#federation)

> [!IMPORTANT]
> Make sure you open the correct ports between VCN's. Remember that this automation will not open port on an existing VCN
> `slurmdbd` runs on port 6819 and `slurmctld` runs on port 6817 by default

If checked, the deployment will take an existing Munge key and use it to register to slurmdbd already running on an another cluster. `slurmdbd` will not run on this deployment. Theuser can then create a Slurm federation using `sacctmgr`
```
sacctmgr -i list cluster
sacctmgr -i add cluster <CLUSTER_1>
sacctmgr -i add cluster <CLUSTER_2>
sacctmgr show cluster
sacctmgr -i add federation <FEDERATION_NAME> clusters=<CLUSTER_1>,<CLUSTER_2>
scontrol show federation
```
