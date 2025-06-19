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
Allow dynamic-group instance_principal to manage dns in compartment compartmentName
```
or:

```
Allow dynamic-group instance_principal to manage all-resources in compartment compartmentName
```


## Supported OS: 
The stack allowa various combination of OS. Here is a list of what has been tested. We can't guarantee any of the other combination.

|   Controller  |    Compute   |
|---------------|--------------|
|      OL8      |      OL8     |
|      OL8      |      OL7     |
| Ubuntu  22.04 | Ubuntu 22.04 |

When switching to Ubuntu, make sure the username is changed from opc to Ubuntu in the ORM for both the controller and compute nodes. 
## How is resizing different from autoscaling ?
Autoscaling is the idea of launching new clusters for jobs in the queue. 
Resizing a cluster is changing the size of a cluster. In some case growing your cluster may be a better idea, be aware that this may lead to capacity errors. Because Oracle CLoud RDMA is non virtualized, you get much better performance but it also means that we had to build HPC islands and split our capacity across different network blocks.
So while there may be capacity available in the DC, you may not be able to grow your current cluster.  

# Cluster Network Resizing (via resize.sh)

Cluster resizing refers to ability to add or remove nodes from an existing cluster network. Apart from add/remove, the resize.py script can also be used to reconfigure the nodes. 

Resizing of HPC cluster with Cluster Network consist of 2 major sub-steps:
- Add/Remove node (IaaS provisioning) to cluster – uses OCI Python SDK 
- Configure the nodes (uses Ansible)
  -  Configures newly added nodes to be ready to run the jobs
  -  Reconfigure services like Slurm to recognize new nodes on all nodes
  -  Update rest of the nodes, when any node/s are removed (eg: Slurm config, /etc/hosts, etc.)

  Cluster created by the autoscaling script can also be resized by using the flag --cluster_name cluster-1-hpc
 
## resize.sh usage 

The resize.sh is deployed on the controller node as part of the HPC cluster Stack deployment. Unreachable nodes have been causing issues. If nodes in the inventory are unreachable, we will not do cluster modification to the cluster unless --remove_unreachable is also specified. That will terminate the unreachable nodes before running the action that was requested (Example Adding a node) 

```
/opt/oci-hpc/bin/resize.sh -h
usage: resize.sh [-h] [--compartment_ocid COMPARTMENT_OCID]
                 [--cluster_name CLUSTER_NAME] [--nodes NODES [NODES ...]]
                 [--no_reconfigure] [--user_logging] [--force] [--remove_unreachable]
                 [{add,remove,remove_unreachable,list,reconfigure}] [number] [--quiet]
Script to resize the CN

positional arguments:
  {add,remove,remove_unreachable,list,reconfigure}
                              Mode type. add/remove node options, implicitly
                              configures newly added nodes. Also implicitly
                              reconfigure/restart services like Slurm to recognize
                              new nodes. Similarly for remove option, terminates
                              nodes and implicitly reconfigure/restart services like
                              Slurm on rest of the cluster nodes to remove reference
                              to deleted nodes. IMPORTANT: remove or remove_unreachable 
                              means delete the node from the cluster which means terminate 
                              the node. remove_unreachable should be used to remove specific 
                              nodes which are no longer reachable via ssh. It gives you control 
                              on which nodes will be terminated by passing the --nodes parameter.
number                        Number of nodes to add or delete if a list of
                              hostnames is not defined.

optional arguments:
  -h, --help            show this help message and exit
  --compartment_ocid COMPARTMENT_OCID
                        OCID of the compartment, defaults to the Compartment
                        OCID of the localhost
  --cluster_name CLUSTER_NAME
                        Name of the cluster to resize. Defaults to the name
                        included in the controller
  --nodes NODES [NODES ...]
                        List of nodes to delete
  --no_reconfigure      If present. Does not rerun the playbooks
  --user_logging        If present. Use the default settings in ~/.oci/config
                        to connect to the API. Default is using
                        instance_principal
  --force               If present. Nodes will be removed even if the destroy
                        playbook failed
  --ansible_crucial     If present during reconfiguration, only crucial
                        ansible playbooks will be executed on the live nodes.
                        Non live nodes will be removed
  --remove_unreachable  If present, ALL nodes that are not sshable will be terminated 
                        before running the action that was requested (Example Adding a node). 
                        CAUTION: Use this only if you want to remove ALL nodes that 
                        are unreachable. Instead, remove specific nodes that are 
                        unreachable by using positional argument remove_unreachable. 
  --quiet               If present, the script will not prompt for a response when 
                        removing nodes and will not give a reminder to save data 
                        from nodes that are being removed
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

Add three nodes to cluster compute-1-hpc
```
/opt/oci-hpc/bin/resize.sh add 3 --cluster_name compute-1-hpc

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
Remove 3 nodes randomly from compute-1-hpc:  
```
/opt/oci-hpc/bin/resize.sh remove 3 --cluster_name compute-1-hpc

```
or 
Remove 3 nodes randomly from compute-1-hpc but do not prompt for a response when removing the nodes and do not give a reminder to save data 
from nodes that are being removed :  
```
/opt/oci-hpc/bin/resize.sh remove 3 --cluster_name compute-1-hpc --quiet

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
And in /etc/ansible/hosts, below value should be true
```
autoscaling = true
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

- cpu-bind: On Ubuntu 22.04, we are switching to Cgroup v2 and we did notice that when hyperthreading is turned off. The default cpu-bind may give some issues. If you get an error like `error: task_g_set_affinity: Invalid argument`, you can try running your job with --cpu-bind=none or --cpu-bind=sockets
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

To do it manually, in your browser of choice, navigate to controllerIP:3000. Username and password are admin/admin, you can change those during your first login. Go to Configuration -> Data Sources. Select autoscaling. Enter Password as Monitor1234! and click on 'Save & test'. Now click on the + sign on the left menu bar and select import. Click on Upload JSON file and upload the file the is located at `/opt/oci-hpc/playbooks/roles/autoscaling_mon/files/dashboard.json`. Select autoscaling (MySQL) as your datasource. 

You will now see the dashboard. 


# LDAP 
If selected controller host will act as an LDAP server for the cluster. It's strongly recommended to leave default, shared home directory. 
User management can be performed from the controller using ``` cluster ``` command. 
Example of cluster command to add a new user: 
```cluster user add name```
By default, a `privilege` group is created that has access to the NFS and can have sudo access on all nodes (Defined at the stack creation. This group has ID 9876) The group name can be modified.
```cluster user add name --gid 9876```
To avoid generating a user-specific key for passwordless ssh between nodes, use --nossh. 
```cluster user add name --nossh --gid 9876```

# Shared home folder

By default, the home folder is NFS shared directory between all nodes from the controller. You have the possibility to use a FSS to share it as well to keep working if the controller goes down. You can either create the FSS from the GUI. Be aware that it will get destroyed when you destroy the stack. Or you can pass an existing FSS IP and path. If you share an existing FSS, do not use /home as mountpoint. The stack will take care of creating a $nfsshare/home directory and mounting it at /home after copying all the appropriate files. 

# Deploy within a private subnet

If "true", this will create a private endpoint in order for Oracle Resource Manager to configure the controller VM and the future nodes in private subnet(s). 
* If "Use Existing Subnet" is false, Terraform will create 2 private subnets, one for the controller and one for the compute nodes.  
* If "Use Existing Subnet" is also true, the user must indicate a private subnet for the controller VM. For the compute nodes, they can reside in another private subnet or the same private subent as the controller VM. 

The controller VM will reside in a private subnet. Therefore, the creation of a "controller service" (https://docs.oracle.com/en-us/iaas/Content/controller/Concepts/controlleroverview.htm), a VPN or FastConnect connection is required. If a public subnet exists in the VCN, adapting the security lists and creating a jump host can also work. Finally, a Peering can also be established betwen the private subnet and another VCN reachable by the user.



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

## Contributing

This project welcomes contributions from the community. Before submitting a pull request, please [review our contribution guide](./CONTRIBUTING.md)

## Security

Please consult the [security guide](./SECURITY.md) for our responsible security vulnerability disclosure process

## License

Copyright (c) 2018-2020 Oracle and/or its affiliates.

Released under the Universal Permissive License v1.0 as shown at
<https://oss.oracle.com/licenses/upl/>.
