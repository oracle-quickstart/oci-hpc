# Stack to create an HPC cluster. 

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)


## Policies to deploy the stack: 
```
allow service compute_management to use tag-namespace in tenancy
allow service compute_management to manage compute-management-family in tenancy
allow service compute_management to read app-catalog-listing in tenancy
allow group user to manage all-resources in compartment compartmentName
```



## What is cluster autoscaling ?
TODO

## How is resizing different from autoscaling ?
TODO

## Policies for autoscaling or resizing:
As described when you specify your variables, if you select instance-principal as way of authenticating your node, make sure your generate a dynamic group and give the following policies to it: 
```
Allow dynamic-group instance_principal to read app-catalog-listing in tenancy
Allow dynamic-group instance_principal to use tag-namespace in tenancy
```
And also either:

```
Allow dynamic-group instance_principal to manage compute-management-family in compartment compartmentName
Allow dynamic-group instance_principal to manage instance-family in compartment compartmentName
Allow dynamic-group instance_principal to use virtual-network-family in compartment compartmentName
```
or:

`Allow dynamic-group instance_principal to manage all-resources in compartment compartmentName`


# Cluster Network Resizing (via resize.py)

Cluster resizing refers to ability to add or remove nodes from an existing cluster network.  It only applies to nodes with RDMA RoCEv2 (aka: cluster network) NICs, so HPC clusters created using BM.HPC2.36, BM.Optimized3.36 and BM.GPU4.8.  Apart from add/remove, the resize.py script can also be used to reconfigure the nodes. 

Resizing of HPC cluster with Cluster Network consist of 2 major sub-steps:
- Add/Remove node (IaaS provisioning) to cluster – uses OCI Python SDK 
- Configure the nodes (uses Ansible)
  -  Configures newly added nodes to be ready to run the jobs
  -  Reconfigure services like Slurm to recognize new nodes on all nodes
  -  Update rest of the nodes, when any node/s are removed (eg: Slurm config, /etc/hosts, etc.)
 
## resize.py usage 

The resize.py is deployed on the bastion node as part of the HPC cluster Stack deployment.  

```
playbooks/resize.py
```

**Add nodes** 

Consist of the following sub-steps:
- Add node (IaaS provisioning) to cluster – uses OCI Python SDK 
- Configure the nodes (uses Ansible)
  -  Configures newly added nodes to be ready to run the jobs
  -  Reconfigure services like Slurm to recognize new nodes on all nodes

 
```
python3 playbooks/resize.py.aug15 add 1

```

**Remove nodes** 

Consist of the following sub-steps:
- Remove node/s (IaaS termination) from cluster – uses OCI Python SDK 
- Reconfigure rest of the nodes in the cluster  (uses Ansible)
  -  Remove reference to removed node/s on rest of the nodes (eg: update /etc/hosts, slurm configs, etc.)
 

Remove specific node:  
```
python3 playbooks/resize.py.aug15 remove --nodes inst-dpi8e-assuring-woodcock
```
or 

Remove a list of nodes (space seperated):  
```
python3 playbooks/resize.py.aug15 remove --nodes inst-dpi8e-assuring-woodcock inst-ed5yh-assuring-woodcock
```
or 
Remove one node randomly:  
```
python3 playbooks/resize.py.aug15 remove 1
```
or 
Remove 3 nodes randomly:  
```
python3 playbooks/resize.py.aug15 remove 3

```

**Reconfigure nodes** 

This allows users to reconfigure nodes (Ansible tasks) of the cluster.  

If you would like to do a slurm config update on all nodes of the cluster.   

```
python3  playbooks/resize.py.aug15 reconfigure --slurm_only_update true
```

Full reconfiguration of all nodes of the cluster.   This runs the same steps, which are ran when a new cluster is created.   If you manually updated configs which are created/updated as part of cluster configuration, then this command will overwrite your manual changes.   

```
python3 playbooks/resize.py.aug15 reconfigure
```

If you would like to fully reconfigure ONLY a specific node/nodes. 

```
 python3  playbooks/resize.py.aug15  reconfigure [--nodes NODES [NODES ...]]
 Example:  python3  resize.py.aug15 reconfigure --nodes inst-gsezk-topical-goblin inst-jvpps-topical-goblin inst-ytuqj-topical-goblin
```



## Resizing (via OCI console)
**Things to consider:**  
- If you resize from OCI console to reduce cluster network/instance pool size(scale down),  the OCI platform decides which node to terminate (oldest node first)
- OCI console only resizes the Cluster Network/Instance Pool, but it doesn't execute the ansible tasks (HPC Cluster Stack) required to configure the newly added nodes or to update the existing nodes when a node is removed (eg: updating /etc/hosts, slurm config, etc).   



# Autoscaling

The autoscaling will work in a “cluster per job” approach. This means that for job waiting in the queue, we will launch new cluster specifically for that job. Autoscaling will also take care of spinning down clusters. By default, a cluster is left Idle for 10 minutes before shutting down. Autoscaling is achieved with a cronjob to be able to quickly switch from one scheduler to the next. 

To turn on autoscaling: 
Uncomment the line in `crontab -e`:
```
* * * * * /home/opc/autoscaling/crontab/autoscale_slurm.sh >> /home/opc/autoscaling/logs/crontab_slurm.log 2>&1
```

# Submit
How to submit jobs: 
Slurm jobs can be submitted as always but a few more constraints can be set: 
Example in `autoscaling/submit/sleep.sbatch`: 

```
#!/bin/sh
#SBATCH -n 72
#SBATCH --ntasks-per-node 36
#SBATCH --exclusive
#SBATCH --job-name sleep_job
#SBATCH --constraint cluster-size-2,BM.HPC2.36

cd /nfs/scratch
mkdir $SLURM_JOB_ID
cd $SLURM_JOB_ID
MACHINEFILE="hostfile"

# Generate Machinefile for mpi such that hosts are in the same
#  order as if run via srun
#
srun -N$SLURM_NNODES -n$SLURM_NNODES  hostname  > $MACHINEFILE
sed -i 's/$/:36/' $MACHINEFILE

cat $MACHINEFILE
# Run using generated Machine file:
sleep 1000
```

- cluster-size: Since clusters can be reused, you can decide to only use a cluster of exactly the right size. Created cluster will have a feature cluster-size-x. You can set the constraint cluster-size-x to make sure this matches and avoid having a 1 node job using a 16 nodes cluster. 

- shape: You can specify the OCI shape that you’d like to run on as a constraint. This will make sure that you run on the right shape and also generate the right cluster. Shapes are expected to be written in OCI format: BM.HPC2.36, BM.Standard.E3.128, BM.GPU4.8,… 
If you’d like to use flex shapes, you can use VM.Standard.E3.x with x the number of cores that you would like. 

## Clusters folders: 
```
~/autoscaling/clusters/clustername
```

## Logs: 
```
~/autoscaling/logs
```

Each cluster will have his own log with name: `create_clustername_date.log` and `delete_clustername_date.log`
The log of the crontab will be in `crontab_slurm.log`


## Manual clusters: 
You can create and delete your clusters manually. 
### Cluster Creation
```
/home/opc/autoscaling/create_cluster.sh NodeNumber clustername shape Cluster-network-enabled
```
Example: 
```
/home/opc/autoscaling/create_cluster.sh 4 cluster-6-amd3128 BM.Standard.E3.128 false
```

To be registered in slurm, the cluster names must be as such: 
BM.HPC2.36: cluster-i-hpc
BM.Standard2.52: cluster-i-std252
VM.Standard2.x: cluster-i-std2x
BM.Standard.E2.64: cluster-i-amd264
VM.Standard.E2.x: cluster-i-amd2x
BM.Standard.E3.128: cluster-i-amd3128
VM.Standard.E3.x: cluster-i-amd3x
BM.GPU2.2: cluster-i-gpu22
VM.GPU2.1: cluster-i-gpu21
BM.GPU3.8: cluster-i-gpu38
VM.GPU3.x: cluster-i-gpu3x
BM.GPU4.8: cluster-i-gpu48

### Cluster Deletion: 
```
/home/opc/autoscaling/delete_cluster.sh clustername
```


## LDAP 
If selected bastion host will act as an LDAP server for the cluster. It's strongly recommended to leave default, shared home directory. 
User management can be performed from the bastion using ``` cluster ``` command. 
