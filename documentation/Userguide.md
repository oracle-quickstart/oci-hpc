# Stack Usage

## Resizing and autoscaling

* Autoscaling creates a cluster when a job in the slurm queue does not have the required infrastructure and destroys it when the job is finished (after a surviving period of time) if no other job in the slurm queue can use it.
* Resizing modifies the size (the number of nodes) of a cluster.

In some cases, increasing the number of nodes of an existing cluster instead of creating a new one next to it may be seen as a better idea. Because Oracle Cloud RDMA is non-virtualized, nodes are organized in a *node < rack < island < network block < data center* pattern. This provides low latency and high throuput for node communication but it may lead to capacity errors if additional nodes cannot be found in the same network block as the initial cluster. So while there may be capacity available in the Availability Domain (data center), user may not be able to grow its current RDMA cluster. By creating as many *small* RDMA clusters as jobs (potentially in different network blocks), autoscaling mitigates the *out-of-capacity* risk compared to resizing a single *large* RDMA cluster (for which all nodes must reside in the same network block).

## Resizing

### Resizing with resize.sh

> [!NOTE]
> This section might need some improvements. It is now possible to resize directly from the OCI web console thanks to the event/function/queue approach.

Cluster resizing refers to ability to add or remove nodes from an existing cluster network. Apart from add/remove, the `mgmt` command can also be used to reconfigure the nodes. 

Resizing a HPC cluster with Cluster Network consists in 2 major sub-steps:
1. Adding or removing compute node(s) (IaaS provisioning) to the cluster using the OCI Python SDK,
2. Configuring the new compute node(s) using Ansible:
  -  Configures newly added compute nodes to be ready to run slurm jobs,
  -  Reconfigures services such as slurm to discover and add the new compute nodes on all nodes.

### Resizing with mgmt

> [!IMPORTANT]
> If you are using GB200 or GB300 hosts, see special notes above

The `mgmt` tool is deployed on the controller node as part of the HPC Cluster Stack deployment. The full mgmt command help is available [here](documentation/mgmt-help.txt). 

#### Adding nodes

Examples:

* Adding one node:
```
mgmt clusters add add-node --count 1
```
* Adding three nodes to cluster compute-1-hpc:
```
mgmt clusters add add-node --count 3 --cluster compute-1-hpc
```

#### Removing nodes

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

#### Reconfiguring nodes

Reconfiguring nodes of the cluster consists in running specific Ansible tasks on both management and/or compute nodes.

Example:

* Reconfiguring a set of 3 compute nodes (slurm notation):
```
mgmt nodes reconfigure --action compute --nodes GPU-[1,2,3]
```
* Reconfiguring the set of 2 compute nodes on the controller (IPs). This will reconfigure Slurm topology and any other action needed to run on the controller:
```
mgmt nodes reconfigure --action controller --nodes 1.0.0.2,1.0.0.3
```

* Reconfiguring the custom role only on 2 compute nodes on the controller (Serials):
```
mgmt nodes reconfigure --action custom --nodes 2539XNG0J,2539XNG4J
```
## Autoscaling

> [!WARNING]
> Not to be confused with the [Autoscaling service](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/autoscalinginstancepools.htm) from OCI.

If selected during the initial bring up of the cluster, you can create a partition that will bring use Slurm autoscaling (Powering Up/Down) capabilities to add and remove nodes in the partition. 
(https://slurm.schedmd.com/power_save.html)

### Clusters and queues configuration

A configuration file at `/opt/oci-hpc/conf/queues.conf` is created and then imported in the DB. You can use the mgmt tool to add and remove nodes/cluster/queues and login nodes. 

#### Specifying node type and queue

The instance type name must be used as a feature in the slurm job definition to make sure it runs on the right type of node. 
Only one default instance-type per queue and one default queue can be specified. To submit jobs on a non default queue, user must either add the `#SBATCH --partition compute` line to the `.sbatch` file header or specify the queue in the command line:
```
sbatch -p queuename job.sh
```

#### Permanent clusters

When the keyword `permanent` is set to `true`, clusters of this node type can be created but cannot be deleted until it is set to `false`. It is not needed to reconfigure slurm after you change that value in the queue configuration file. 

After a modification of the `/opt/oci-hpc/conf/queues.conf`, user must run the `/opt/oci-hpc/bin/slurm_config.sh` command to make sure that modifications will be taken into account.

Queues and instances configuration can be put back in the initial state with `/opt/oci-hpc/bin/slurm_config.sh --initial`.

#### Autoscaling activation

To turn on autoscaling:
1. Run `crontab -e` and uncomment the following line:
```
* * * * * /opt/oci-hpc/autoscaling/crontab/autoscale_slurm.sh >> /config/logs/crontab_slurm.log 2>&1
```
2. Set `autoscaling = true` in `/etc/ansible/hosts`.

#### Clusters folders

For each cluster, except the permanent one, a cluster folder is created in:
```
/opt/oci-hpc/autoscaling/clusters/clustername
```

## Submiting jobs

Slurm jobs can be submitted as always but a few more constraints can be set: 

Example (`/opt/oci-hpc/samples/submit/` file):

```
#!/bin/sh
#SBATCH -n 72
#SBATCH --ntasks-per-node 36
#SBATCH --exclusive
#SBATCH --job-name sleep_job
#SBATCH --constraint hpc-default

cd /fss
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

## Manual Cluster Management

Clusters can be created and deleted manually (for example when autoscaling is not activated).

### Cluster Creation

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

### Cluster Deletion

To delete a cluster manually, run:
```
/opt/oci-hpc/bin/delete_cluster.sh clustername
```
If something goes wrong during the deletion process, the deletion can be forced with the `FORCE` option:
```
/opt/oci-hpc/bin/delete_cluster.sh clustername FORCE
```
If the cluster is already being destroyed, there will be a `currently_destroying` file in the cluster folder (`/opt/oci-hpc/autoscaling/clusters/clustername`).

## Logs

The infrastructure logs are stored in:
```
/config/logs
```

Each cluster has its own log file with named `create_clustername_date.log` and `delete_clustername_date.log` for its creation and deletion processes. The logs of the crontab is stored in `crontab_slurm.log`.