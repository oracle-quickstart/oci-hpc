# Stack to create an HPC cluster. 

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)


## Policies to deploy the stack: 
```
allow service compute_management to use tag-namespace in tenancy
allow service compute_management to manage compute-management-family in tenancy
allow service compute_management to read app-catalog-listing in tenancy
allow group user to manage all-resources in compartment compartmentName
```
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
Allow dynamic-group instance_principal to use volumes in compartment compartmentName
```
or:

`Allow dynamic-group instance_principal to manage all-resources in compartment compartmentName`

## How is resizing different from autoscaling ?
Autoscaling is the idea of launching new clusters for jobs in the queue. 
Resizing a cluster is changing the size of a cluster. In some case growing your cluster may be a better idea, be aware that this may lead to capacity errors. Because Oracle CLoud RDMA is non virtualized, you get much better performance but it also means that we had to build HPC islands and split our capacity across different network blocks.
So while there may be capacity available in the DC, you may not be able to grow your current cluster.  

# Cluster Network Resizing (via resize.sh)

Cluster resizing refers to ability to add or remove nodes from an existing cluster network.  It only applies to nodes with RDMA RoCEv2 (aka: cluster network) NICs, so HPC clusters created using BM.HPC2.36, BM.Optimized3.36 and BM.GPU4.8.  Apart from add/remove, the resize.py script can also be used to reconfigure the nodes. 

Resizing of HPC cluster with Cluster Network consist of 2 major sub-steps:
- Add/Remove node (IaaS provisioning) to cluster – uses OCI Python SDK 
- Configure the nodes (uses Ansible)
  -  Configures newly added nodes to be ready to run the jobs
  -  Reconfigure services like Slurm to recognize new nodes on all nodes
  -  Update rest of the nodes, when any node/s are removed (eg: Slurm config, /etc/hosts, etc.)

  Cluster created by the autoscaling script can also be resized by using the flag --cluster_name cluster-1-hpc
 
## resize.sh usage 

The resize.py is deployed on the bastion node as part of the HPC cluster Stack deployment.  

```
/opt/oci-hpc/bin/resize.sh -h
usage: resize.sh [-h] [--compartment_ocid COMPARTMENT_OCID]
                 [--cluster_name CLUSTER_NAME] [--nodes NODES [NODES ...]]
                 [--no_reconfigure] [--user_logging] [--force]
                 [{add,remove,list,reconfigure}] [number]

Script to resize the CN

positional arguments:
  {add,remove,list,reconfigure}
                        Mode type. add/remove node options, implicitly
                        configures newly added nodes. Also implicitly
                        reconfigure/restart services like Slurm to recognize
                        new nodes. Similarly for remove option, terminates
                        nodes and implicitly reconfigure/restart services like
                        Slurm on rest of the cluster nodes to remove reference
                        to deleted nodes.
  number                Number of nodes to add or delete if a list of
                        hostnames is not defined

optional arguments:
  -h, --help            show this help message and exit
  --compartment_ocid COMPARTMENT_OCID
                        OCID of the compartment, defaults to the Compartment
                        OCID of the localhost
  --cluster_name CLUSTER_NAME
                        Name of the cluster to resize. Defaults to the name
                        included in the bastion
  --nodes NODES [NODES ...]
                        List of nodes to delete
  --no_reconfigure      If present. Does not rerun the playbooks
  --user_logging        If present. Use the default settings in ~/.oci/config
                        to connect to the API. Default is using
                        instance_principal
  --force               If present. Nodes will be removed even if the destroy
                        playbook failed

```

**Add nodes** 

Consist of the following sub-steps:
- Add node (IaaS provisioning) to cluster – uses OCI Python SDK 
- Configure the nodes (uses Ansible)
  -  Configures newly added nodes to be ready to run the jobs
  -  Reconfigure services like Slurm to recognize new nodes on all nodes

Add one node 
```
/opt/oci-hpc/bin/resize.sh add 1

```

Add three nodes
```
/opt/oci-hpc/bin/resize.sh add 3

```


**Remove nodes** 

Consist of the following sub-steps:
- Remove node/s (IaaS termination) from cluster – uses OCI Python SDK 
- Reconfigure rest of the nodes in the cluster  (uses Ansible)
  -  Remove reference to removed node/s on rest of the nodes (eg: update /etc/hosts, slurm configs, etc.)
 

Remove specific node:  
```
/opt/oci-hpc/bin/resize.sh remove --nodes inst-dpi8e-assuring-woodcock
```
or 

Remove a list of nodes (space seperated):  
```
/opt/oci-hpc/bin/resize.sh remove --nodes inst-dpi8e-assuring-woodcock inst-ed5yh-assuring-woodcock
```
or 
Remove one node randomly:  
```
/opt/oci-hpc/bin/resize.sh remove 1
```
or 
Remove 3 nodes randomly:  
```
/opt/oci-hpc/bin/resize.sh remove 3

```

**Reconfigure nodes** 

This allows users to reconfigure nodes (Ansible tasks) of the cluster.  

Full reconfiguration of all nodes of the cluster.   This will run the same steps, which are ran when a new cluster is created.   If you manually updated configs which are created/updated as part of cluster configuration, then this command will overwrite your manual changes.   

```
/opt/oci-hpc/bin/resize.sh reconfigure
```



## Resizing (via OCI console)
**Things to consider:**  
- If you resize from OCI console to reduce cluster network/instance pool size(scale down),  the OCI platform decides which node to terminate (oldest node first)
- OCI console only resizes the Cluster Network/Instance Pool, but it doesn't execute the ansible tasks (HPC Cluster Stack) required to configure the newly added nodes or to update the existing nodes when a node is removed (eg: updating /etc/hosts, slurm config, etc).   


# Autoscaling

The autoscaling will work in a “cluster per job” approach. This means that for job waiting in the queue, we will launch new cluster specifically for that job. Autoscaling will also take care of spinning down clusters. By default, a cluster is left Idle for 10 minutes before shutting down. Autoscaling is achieved with a cronjob to be able to quickly switch from one scheduler to the next.

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
* * * * * /opt/oci-hpc/autoscaling/crontab/autoscale_slurm.sh >> /opt/oci-hpc/logs/crontab_slurm.log 2>&1
```

# Submit
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

## Clusters folders: 
```
/opt/oci-hpc/autoscaling/clusters/clustername
```

## Logs: 
```
/opt/oci-hpc/logs
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
The name of the cluster must be
queueName-clusterNumber-instanceType_keyword

The keyword will need to match the one from /opt/oci-hpc/conf/queues.conf to be regirstered in Slurm

### Cluster Deletion: 
```
/opt/oci-hpc/bin/delete_cluster.sh clustername
```

In case something goes wrong during the deletion, you can force the deletion with 
```
/opt/oci-hpc/bin/delete_cluster.sh clustername FORCE
```
When the cluster is already being destroyed, it will have a file `/opt/oci-hpc/autoscaling/clusters/clustername/currently_destroying` 

## Autoscaling Monitoring
If you selected the autoscaling monitoring, you can see what nodes are spinning up and down as well as running and queued jobs. Everything will run automatically except the import of the Dashboard in Grafana due to a problem in the Grafana API. 

To do it manually, in your browser of choice, navigate to bastionIP:3000. Username and password are admin/admin, you can change those during your first login. Click on the + sign on the left menu bar and select import. Click on Upload JSON file and upload the file the is located at `/opt/oci-hpc/playbooks/roles/autoscaling_mon/files/dashboard.json`. Select autoscaling (MySQL) as your datasource. 

You will now see the dashboard. 


# LDAP 
If selected bastion host will act as an LDAP server for the cluster. It's strongly recommended to leave default, shared home directory. 
User management can be performed from the bastion using ``` cluster ``` command. 
Example of cluster command to add a new user: 
```cluster user add name```
By default, a `privilege` group is created that has access to the NFS and can have sudo access on all nodes (Defined at the stack creation. This group has ID 9876) The group name can be modified.
```cluster user add name --gid 9876```
To generate a user-specific key for passwordless ssh between nodes, use --ssh. 
```cluster user add name --ssh --gid 9876```

# Shared home folder

By default, the home folder is NFS shared directory between all nodes from the bastion. You have the possibility to use a FSS to share it as well to keep working if the bastion goes down. You can either create the FSS from the GUI. Be aware that it will get destroyed when you destroy the stack. Or you can pass an existing FSS IP and path. If you share an existing FSS, do not use /home as mountpoint. The stack will take care of creating a $nfsshare/home directory and mounting it at /home after copying all the appropriate files.  


