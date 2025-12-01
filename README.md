# Stack to create an HPC cluster. 

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)

## Introduction
This Terraform stack is intended to be used in [Oracle Resource Manager](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/resourcemanager.htm). It makes use of different OCI services described in the section [cloud services used](#cloud-services-used). The goal is to deploy and configure a HPC/GPU cluster with at minimum a controller node with compute nodes residing in a [Virtual Cloud Network](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/overview.htm) (VCN). The following diagram shows the target architecture:

![Target architecture deployed via this Terraform stack.](/images/architecture_diagram.png)

## Cloud services used and considerations before deployment
### Cloud services used
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


> [!WARNING]
> Be sure to have the appropriate limit for each service that is used. In case you reach *limit exceeded*, you can create a [Service Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/GSG/support/create-incident-limit.htm)

### Considerations 
**Serverless part** 

This implementation uses [Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm) and [Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm) to communicate the status of the nodes to a [Queue](https://docs.oracle.com/en-us/iaas/Content/queue/overview.htm). The creation of the function requires an [Auth Token](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrygettingauthtoken.htm) to authenticate to the [Oracle registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm) where the function image is stored. Auth tokens are limited and an existing one can be specified during the configuration.

> [!WARNING]
> Auth token are limited to "2" per user by default. It is recommended to use an existing Auth Token that can be created in your home region prior to the stack deployment. In case you do not select *"Use existing auth token"*, a Auth Token will be created. Please note that after the creation, some time (up to 5mins) is needed for the Auth Token to be valid to authenticate with `docker login`. This is why a `time_sleep` resource is executed in terraform.

**Using an existing VCN**

This implementation uses Private DNS view. When using an existing VCN, make sure you have a private zone with `<cluster-name>.local`. You also must create the correct DCHP options set to `Internet and VCN Resolver`, `Custom Search Domain` with the search domain corresponding to `<cluster-name>.local`. Finally, the DHCP options of the different subnets must be set to the newly created DCHP options and not "Default DHCP Options..."

> [!WARNING]
> If the DHCP options and the private zone are not set properly, the deployment will fail. Make sure they exist or do not use an existing VCN and deploy a new one with this stack.

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
### Policies for function 
The function makes use of [Resource Principals](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm) to manage different resources in the compartment. For the function to work, you need to create a [dynamic group](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/To_create_a_dynamic_group.htm) and grant it access to manage resources in this compartment. Example with dynamic group *fn_dg*:

```
ALL {resource.type = 'fnfunc', resource.compartment.id = 'ocid1.compartment.oc1..aaaXXXX'}
```

With the following policy:

```
Allow dynamic-group fn_dg to manage all-resources in compartment compartmentName
```

### Policies for queues 
In order to read messages from the OCI queue service, the controller and compute nodes need to be part of a dynamic group with the adequate policies (see [instance principals](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm)).

Example with the dynamic group *instance_principal*. If the dynamic group is created in a different identity domain, you will have to use IdentityDomainName/DynamicGroupName in the policies. 

```
All {instance.compartment.id = 'ocid1.compartment.oc1..aaaXXXX'}
```

With the following policies:
```
Allow dynamic-group instance_principal to use queue-push in compartment CompartmentName
Allow dynamic-group instance_principal to use queue-pull in compartment CompartmentName
allow dynamic-group instance_principal to manage queues in compartment CompartmentName
```

### Policies for resizing or adding clusters:
As described when you specify your variables, if you select instance-principal as way of authenticating your node, make sure your generate a dynamic group including one or more instance in a compartment and all the functions of the compartment. Example with the dynamic group *instance_principal*. If the dynamic group is created in a different identity domain, you will have to use IdentityDomainName/

```
All {instance.compartment.id = 'ocid1.compartment.oc1..aaaXXXX'}
```

Give the following policies to it:

```
Allow dynamic-group instance_principal to read app-catalog-listing in tenancy
Allow dynamic-group instance_principal to use tag-namespace in tenancy
```
And also either:

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
### Policies for Host API:
The capacity topology usually gets created by default in the root compartment. To be able to access it, you need to add the folowing policy: 
```
Allow dynamic-group instance_principal to manage compute-bare-metal-hosts in tenancy
```


## Supported OS: 
The stack allows a various combination of OS. Here is a list of what has been tested. We can't guarantee any of the other combination.

|   Controller  |    Compute   |
|---------------|--------------|
|      OL8      |      OL8     |
|      OL9      |      OL9     |
| Ubuntu  22.04 | Ubuntu 22.04 |
| Ubuntu  24.04 | Ubuntu 24.04 |

When switching to Ubuntu, make sure the username is changed from `opc` to `ubuntu` in ORM for both the controller and compute nodes. 

## Workflow

![Workflow for node configuration](/images/workflow.png)

### Serverless function
When nodes are added/removed, this triggers an event which triggers an OCI function. This serverless function will register nodes in the DNS and change the OCI display name to the Slurm name if `Change hostname` is set to `true` in the configuration. The current approach is using the Oracle DNS service instead of the `/etc/hosts`

When a node is created:
  * Send a message to the queue with the IP of the node and status 'starting'
  * Add DNS entry (hostname_convention must be a tag)
  * Change the OCI display name to the Slurm name (if option checked)

When a node is deleted:
  * Send a message to the queue with the IP of the node and status 'terminating'
  * Remove DNS entry 

### Node configuration
Each compute node will run an Ansible script locally. The nodes will be tagged with the name of the controller they belong to. That node will mount a nfs `/config` folder to get the Ansible Playbooks and the keys. The ansible playbook will run all the tasks that can be run on the host where one task creates a small HTTP server that boradcasts information on port 9876. Here is an example of the information:
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

### Controller service and actions for configuration
The Controller is running a service that will read messages in the queue and store the information in a MySQL database. It also queries the information of the webservers of the compute nodes and add this to the database as well. Finally, it runs ansible roles locally when the nodes are marked as "Ready" in order to finalise the cluster setup:
  * run role `Fix_ldap`
  * Add/remove the node to prometheus.yml
  * Add/remove the node in slurm configuration i.e. topology.conf and gres.conf

## Notes on Deployments for Memory Fabric Based Shapes, such as Nvidia GB200 / GB300
When deploying this shape you should configure and deploy the stack as usual EXCEPT that the initial size of the cluster should to be set to 0, but otherwise fully define the instance configuration for the compute hosts in the stack deployment.  Once you log into the cluster controller you can create the initial GPU Memory Cluster like this.

First check that the lifecycle_state is AVAILABLE, the fabric_health needs to be HEALTHY, and check AVAILABLE nodes:
```
mgmt fabrics list
```

Now use the OCID from above for --fabric, as well as the number of AVAILABLE hosts for --count:
```
mgmt clusters create --count 16 --cluster my_cluster --instancetype default --fabric ocid1.computegpumemoryfabric.oc1..... 
```

This should create a computegpumemorycluster with a name like cluster_xxxxx, as well as stand up the number of instances given in --count.  You should see this reflected in ```mgmt fabrics list``` after a few minutes.

Use the above command to add ONLY THE FIRST SET OF INSTANCES.  See below on how to add additional gpumemoryfabrics to the compute cluster named my_cluster that was created above (otherwise inter-rack communication will not work).

To instantiate more hosts from this same computegpumemoryfabric to this cluster, do this with the corresponding cluster_xxxxx name for these hosts as shown as memory_cluster_name in ```mgmt fabrics list```:
```
mgmt clusters add node --count 2 --memorycluster cluster_xxxxx
```

To add hosts from other computegpumemoryfabrics to the cluster:
```
mgmt clusters add memory-fabric --count 18 --cluster my_cluster --instancetype default --fabric ocid1.computegpumemoryfabric.oc1.... 
```

To delete a computegpumemorycluster and terminate all of the instances:
```
mgmt clusters delete --memory_cluster cluster_xxxxx
```

## How is resizing different from autoscaling ?
Autoscaling is the idea of launching new clusters for jobs in the queue. 
Resizing a cluster is changing the size of a cluster. In some case growing your cluster may be a better idea, be aware that this may lead to capacity errors. Because Oracle Cloud RDMA is non virtualized, you get much better performance but it also means that we had to build HPC islands and split our capacity across different network blocks.
So while there may be capacity available in the DC, you may not be able to grow your current cluster.  

## Cluster Network Resizing (via resize.sh)
> [!NOTE]
> This section might need some improvements. It is now possible to resize directly from the OCI web console thanks to the event/function/queue approach.

Cluster resizing refers to ability to add or remove nodes from an existing cluster network. Apart from add/remove, the mgmt tool can also be used to reconfigure the nodes. 

Resizing of HPC cluster with Cluster Network consist of 2 major sub-steps:
- Add/Remove node (IaaS provisioning) to cluster – uses OCI Python SDK 
- Configure the nodes (uses Ansible)
  -  Configures newly added nodes to be ready to run the jobs
  -  Reconfigure services like Slurm to recognize new nodes on all nodes


### Using mgmt to resize the cluster
> [!IMPORTANT]
> If you are using GB200 or GB300 hosts, see special notes above

The mgmt tool is deployed on the controller node as part of the HPC cluster Stack deployment. 

**Add nodes** 

Add one node 
```
mgmt clusters add add-node --count 1
```


Add three nodes to cluster compute-1-hpc
```
mgmt clusters add add-node --count 3 --cluster compute-1-hpc
```


**Remove nodes** 

Consist of the following sub-steps:
- Remove node/s (IaaS termination) from cluster – uses OCI Python SDK 
- Reconfigure rest of the nodes in the cluster  (uses Ansible)
  -  Remove reference to removed node/s on rest of the nodes (eg: update /etc/hosts, slurm configs, etc.)
 

Remove specific node:  
```
mgmt nodes terminate --nodes GPU-123
```
or 

Remove a list of nodes (comma separated):  
```
mgmt nodes terminate --nodes GPU-123,GPU-456
```

Remove a list of nodes (SLURM notation):  
```
mgmt nodes terminate --nodes GPU-[123,456]
```

**Reconfigure nodes** 

This allows users to reconfigure nodes (Ansible tasks) of the cluster.  
```
mgmt nodes reconfigure compute --nodes GPU-[1,2,3]
```


## Autoscaling
> [!WARNING]
> Not to be confused with the [Autoscaling service](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/autoscalinginstancepools.htm) from OCI.

The autoscaling will work in a “cluster per job” approach. This means that for job waiting in the queue, we will launch a new cluster specifically for that job. Autoscaling will also take care of spinning down clusters. By default, a cluster is left Idle for 10 minutes before shutting down. Autoscaling is achieved with a cronjob to be able to quickly switch from one scheduler to the next.

Smaller jobs can run on large clusters and the clusters will be resized down after the grace period to only the running nodes. Cluster will NOT be resized up. We will spin up a new larger cluster and spin down the smaller cluster to avoid capacity issues in the HPC island. 

Initial cluster deployed through the stack will never be spun down.

There is a configuration file at `/opt/oci-hpc/conf/queues.conf` with an example at `/opt/oci-hpc/conf/queues.conf.example`to show how to add multiple queues and multiple instance types. Examples are included for HPC, GPU or Flex VMs. 

You will be able to use the instance type name as a feature in the job definition to make sure it runs/create the right kind of node. 

You can only have one default instance-type per queue and one default queue. To submit to a non default queue, either add this line to the SBATCH file: `#SBATCH --partition compute` or in the command line: `sbatch -p queuename job.sh`

The key word `permanent` allows will spin up clusters but not delete them untill it is set to false. It is not needed to reconfigure slurm after you change that value. 

After a modification of the `/opt/oci-hpc/conf/queues.conf`, you need to run 
`/opt/oci-hpc/bin/slurm_config.sh`

If you have some state that is messing with Slurm, you can make sure it is put back in the initial state with 
`/opt/oci-hpc/bin/slurm_config.sh --initial`

To turn on autoscaling: 
Uncomment the line in `crontab -e`:
```
* * * * * /opt/oci-hpc/autoscaling/crontab/autoscale_slurm.sh >> /config/logs/crontab_slurm.log 2>&1
```
And in /etc/ansible/hosts, below value should be true
```
autoscaling = true
```

## Submit
How to submit jobs: 
Slurm jobs can be submitted as always but a few more constraints can be set: 
Example in `/opt/oci-hpc/samples/submit/`: 

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
#  order as if run via srun
#
scontrol show hostnames $SLURM_JOB_NODELIST > $MACHINEFILE
sed -i "s/$/:${SLURM_NTASKS_PER_NODE}/" $MACHINEFILE

cat $MACHINEFILE
# Run using generated Machine file:
sleep 1000
```
 
- Instance Type: You can specify the OCI instance type that you’d like to run on as a constraint. This will make sure that you run on the right shape and also generate the right cluster. Instance types are defined in the `/opt/oci-hpc/conf/queues.conf` file in yml format. Leave all of the field in there even if they are not used. You can define multiple queues and multiple instance type in each queue. If you do not select an instance type when creating your job, it will use the default one.

- cpu-bind: On Ubuntu 22.04, we are switching to Cgroup v2 and we did notice that when hyperthreading is turned off. The default cpu-bind may give some issues. If you get an error like `error: task_g_set_affinity: Invalid argument`, you can try running your job with --cpu-bind=none or --cpu-bind=sockets
## Clusters folders: 
```
/opt/oci-hpc/autoscaling/clusters/clustername
```

## Logs: 
```
/config/logs
```

Each cluster will have his own log with name: `create_clustername_date.log` and `delete_clustername_date.log`
The log of the crontab will be in `crontab_slurm.log`


## Manual clusters: 
You can create and delete your clusters manually. 
### Cluster Creation
```
/opt/oci-hpc/bin/create_cluster.sh NodeNumber clustername instance_type queue_name
```
Example: 
```
/opt/oci-hpc/bin/create_cluster.sh 4 compute2-1-hpc HPC_instance compute2
```

### Cluster Deletion: 
```
/opt/oci-hpc/bin/delete_cluster.sh clustername
```

In case something goes wrong during the deletion, you can force the deletion with 
```
/opt/oci-hpc/bin/delete_cluster.sh clustername FORCE
```
When the cluster is already being destroyed, it will have a file `/opt/oci-hpc/autoscaling/clusters/clustername/currently_destroying` 

## LDAP 
If selected controller host will act as an LDAP server for the cluster. It's strongly recommended to leave default, shared home directory. 
User management can be performed from the controller using ``` cluster ``` command. 
Example of cluster command to add a new user: 
```cluster user add name```
By default, a `privilege` group is created that has access to the NFS and can have sudo access on all nodes (Defined at the stack creation. This group has ID 9876) The group name can be modified.
```cluster user add name --gid 9876```
To avoid generating a user-specific key for passwordless ssh between nodes, use --nossh. 
```cluster user add name --nossh --gid 9876```

## Shared home folder
By default, the home folder is NFS shared directory between all nodes from the controller. You have the possibility to use a FSS to share it as well to keep working if the controller goes down. You can either create the FSS from the GUI. Be aware that it will get destroyed when you destroy the stack. Or you can pass an existing FSS IP and path. If you share an existing FSS, do not use /home as mountpoint. The stack will take care of creating a $nfsshare/home directory and mounting it at /home after copying all the appropriate files. 

## Deploy within a private subnet
If `true`, this will create a private endpoint in order for Oracle Resource Manager to configure the controller VM and the future nodes in private subnet(s). 
* If "Use Existing Network" is false, Terraform will create 2 private subnets, one for the controller and one for the compute nodes.  
* If "Use Existing Network" is true, the user must indicate a private subnet for the controller VM. For the compute nodes, they can reside in another private subnet or the same private subent as the controller VM. 

> [!IMPORTANT]
> The controller VM will reside in a private subnet. Therefore, the creation of a [bastion service](https://docs.public.content.oci.oraclecloud.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm), a VPN or FastConnect connection is required. If a public subnet exists in the VCN, adapting the security lists and creating a jump host can also work. Finally, a Peering can also be established betwen the private subnet and another VCN reachable by the user.

## Create a back-up Slurm Controller
> [!IMPORTANT]
> FSS must be used to have a shared directory for the state

If checked, creates a managed MySQL database via [MySQL Heatwave](https://docs.oracle.com/en-us/iaas/mysql-database/home.htm). 
In the configuration of Slurm, the controller and the backup each have `slurmctld` (with [SlurmctldHost](https://slurm.schedmd.com/slurm.conf.html#OPT_SlurmctldHost) defined twice as controller and backup, [AccountingStorageHost](https://slurm.schedmd.com/slurm.conf.html#OPT_AccountingStorageHost) pointing to the controller and [AccountingStorageBackupHost](https://slurm.schedmd.com/slurm.conf.html#OPT_AccountingStorageBackupHost) pointing to the backup in `slurm.conf`) and `slurmdbd` (with [DbdHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_DbdHost) pointing to the controller, [DbdBackupHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_DbdBackupHost) pointing to the backup and [StorageHost](https://slurm.schedmd.com/slurmdbd.conf.html#OPT_StorageHost) pointing to MySQL Heatwave in `slurmdbd.conf`) running. Both the controller and the backup can querry the database if one of them is down.


## max_nodes_partition.py usage 
Use the alias "max_nodes" to run the python script max_nodes_partition.py. You can run this script only from controller.

$ max_nodes --> Information about all the partitions and their respective clusters, and maximum number of nodes distributed evenly per partition

$ max_nodes --include_cluster_names xxx yyy zzz --> where xxx, yyy, zzz are cluster names. Provide a space separated list of cluster names to be considered for displaying the information about clusters and maximum number of nodes distributed evenly per partition


## validation.py usage
Use the alias "validate" to run the python script validation.py. You can run this script only from controller. 

The script performs these checks. 
-> Check the number of nodes is consistent across resize, /etc/hosts, slurm, topology.conf, OCI console, inventory files.
-> PCIe bandwidth check 
-> GPU Throttle check 
-> Check whether md5 sum of /etc/hosts file on nodes matches that on controller

Provide at least one argument: [-n NUM_NODES] [-p PCIE] [-g GPU_THROTTLE] [-e ETC_HOSTS]

Optional argument with [-n NUM_NODES] [-p PCIE] [-g GPU_THROTTLE] [-e ETC_HOSTS]: [-cn CLUSTER_NAMES]
Provide a file that lists each cluster on a separate line for which you want to validate the number of nodes and/or pcie check and/or gpu throttle check and/or /etc/hosts md5 sum. 

For pcie, gpu throttle, and /etc/hosts md5 sum check, you can either provide y or Y along with -cn or you can give the hostfile path (each host on a separate line) for each argument. For number of nodes check, either provide y or give y along with -cn.

Below are some examples for running this script.

validate -n y --> This will validate that the number of nodes is consistent across resize, /etc/hosts, slurm, topology.conf, OCI console, inventory files. The clusters considered will be the default cluster if any and cluster(s) found in /opt/oci-hpc/autoscaling/clusters directory. The number of nodes considered will be from the resize script using the clusters we got before. 

validate -n y -cn <cluster name file> --> This will validate that the number of nodes is consistent across resize, /etc/hosts, slurm, topology.conf, OCI console, inventory files. It will also check whether md5 sum of /etc/hosts file on all nodes matches that on controller. The clusters considered will be from the file specified by -cn option. The number of nodes considered will be from the resize script using the clusters from the file. 

validate -p y -cn <cluster name file> --> This will run the pcie bandwidth check. The clusters considered will be from the file specified by -cn option. The number of nodes considered will be from the resize script using the clusters from the file. 

validate -p <pcie host file> --> This will run the pcie bandwidth check on the hosts provided in the file given. The pcie host file should have a host name on each line.

validate -g y -cn <cluster name file> --> This will run the GPU throttle check. The clusters considered will be from the file specified by -cn option. The number of nodes considered will be from the resize script using the clusters from the file. 

validate -g <gpu check host file> --> This will run the GPU throttle check on the hosts provided in the file given. The gpu check host file should have a host name on each line.

validate -e y -cn <cluster name file> --> This will run the /etc/hosts md5 sum check. The clusters considered will be from the file specified by -cn option. The number of nodes considered will be from the resize script using the clusters from the file. 

validate -e <md5 sum check host file> --> This will run the /etc/hosts md5 sum check on the hosts provided in the file given. The md5 sum check host file should have a host name on each line.

You can combine all the options together such as:
validate -n y -p y -g y -e y -cn <cluster name file>


## /opt/oci-hpc/scripts/collect_logs.py
This is a script to collect nvidia bug report, sosreport, console history logs. 

The script needs to be run from the controller. In the case where the host is not ssh-able, it will get only  console history logs for the same.

It requires the below argument.
--hostname <HOSTNAME>

And --compartment-id <COMPARTMENT_ID> is optional (i.e. assumption is the host is in the same compartment as the controller). 

Where HOSTNAME is the node name for which you need the above logs and COMPARTMENT_ID is the OCID of the compartment where the node is.

The script will get all the above logs and put them in a folder specific to each node in /home/{user}. It will give the folder name as the output.

Assumption: For getting the console history logs, the script expects to have the node name in /etc/hosts file.

Examples:

python3 collect_logs.py --hostname compute-permanent-node-467
The nvidia bug report, sosreport, and console history logs for compute-permanent-node-467 are at /home/ubuntu/compute-permanent-node-467_06132023191024

python3 collect_logs.py --hostname inst-jxwf6-keen-drake
The nvidia bug report, sosreport, and console history logs for inst-jxwf6-keen-drake are at /home/ubuntu/inst-jxwf6-keen-drake_11112022001138

for x in `less /home/opc/hostlist` ; do echo $x ; python3 collect_logs.py --hostname $x; done ;
compute-permanent-node-467
The nvidia bug report, sosreport, and console history logs for compute-permanent-node-467 are at /home/ubuntu/compute-permanent-node-467_11112022011318
compute-permanent-node-787
The nvidia bug report, sosreport, and console history logs for compute-permanent-node-787 are at /home/ubuntu/compute-permanent-node-787_11112022011835

Where hostlist had the below contents
compute-permanent-node-467
compute-permanent-node-787


## Collect RDMA NIC Metrics and Upload to Object Storage
OCI-HPC is deployed in customer tenancy. So, OCI service teams cannot access metrics from these OCI-HPC stack clusters. Due to overcome this issue, in release,
we introduce a feature to collect RDMA NIC Metrics and upload those metrics to Object Storage. Later on, that Object Storage URL could be shared with OCI service
teams. After that URL, OCI service teams could access metrics and use those metrics for debugging purpose.

To collect RDMA NIC Metrics and upload those to Object Storage, user needs to follow these following steps:

Step 1: Create a PAR (PreAuthenticated Request)
For creating a PAR, user needs to select check-box "Create Object Storage PAR" during Resource Manager's stack creation.
By default, this check box is enabled. By selecting, this check-box, a PAR would be created.

Step 2: Use shell script: upload_rdma_nic_metrics.sh to collect metrics and upload to object storage.
User needs to use shell script: upload_rdma_nic_metrics.sh to collect metrics and upload to object storage. User could configure metrics
collection limit and interval through config file: rdma_metrics_collection_config.conf.

## Meshpinger
Meshpinger is a tool for validating network layer connectivity between RDMA NICs on a cluster network in OCI. The tool is capable of initiating ICMP ping from every RDMA NIC port on the cluster network to every other RDMA NIC port on the same cluster network and
reporting back the success/failure status of the pings performed in the form of logs

Running the tool before starting workload on a cluster network should serve as a good precheck step to gain confidence on the network reachability between RDMA NICs. Typical causes for reachability failures that the tool can help pinpoint are,
1. Link down on the RDMA NIC
2. RDMA interface initialization or configuration issues including IP address assignment to
the interface
3. Insufficient ARP table size on the node to store all needed peer mac addresses
