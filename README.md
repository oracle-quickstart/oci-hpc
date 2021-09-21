# Stack to create an HPC cluster. 

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https://github.com/oracle-quickstart/oci-hpc/archive/refs/heads/master.zip)


## Policies to deploy the stack: 
```
allow service compute_management to use tag-namespace in tenancy
allow service compute_management to manage compute-management-family in tenancy
allow service compute_management to read app-catalog-listing in tenancy
allow group user to manage all-resources in compartment compartmentName
```

## What is cluster resizing (resize.py) ?
TODO

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


# Resizing (via resize.py or OCI console)
TODO


# Autoscaling

The autoscaling will work in a “cluster per job” approach. This means that for job waiting in the queue, we will launch new cluster specifically for that job. Autoscaling will also take care of spinning down clusters. By default, a cluster is left Idle for 10 minutes before shutting down. Autoscaling is achieved with a cronjob to be able to quickly switch from one scheduler to the next.

Initial cluster deployed through the stack will never be spun down.

There is a configuration file at `/opt/oci-hpc/autoscaling/queues.conf` with an example at `/opt/oci-hpc/autoscaling/queues.conf.example`to show how to add multiple queues and multiple instance types. Examples are included for HPC, GPU or Flex VMs. 

You will be able to use the instance type name as a feature in the job definition to make sure it runs/create the right kind of node. 

You can only have one default instance-type per queue and one default queue. To submit to a non default queue, either add this line to the SBATCH file: `#SBATCH --partition compute` or in the command line: `sbatch -p queuename job.sh`

The key word `permanent` allows will spin up clusters but not delete them untill it is set to false. It is not needed to reconfigure slurm after you change that value. 

After a modification of the `/opt/oci-hpc/autoscaling/queues.conf`, you need to run 
`/opt/oci-hpc/autoscaling/slurm_config.sh`

To turn on autoscaling: 
Uncomment the line in `crontab -e`:
```
* * * * * /opt/oci-hpc/autoscaling/crontab/autoscale_slurm.sh >> /opt/oci-hpc/autoscaling/logs/crontab_slurm.log 2>&1
```

# Submit
How to submit jobs: 
Slurm jobs can be submitted as always but a few more constraints can be set: 
Example in `/opt/oci-hpc/autoscaling/submit/`: 

```
#!/bin/sh
#SBATCH -n 72
#SBATCH --ntasks-per-node 36
#SBATCH --exclusive
#SBATCH --job-name sleep_job
#SBATCH --constraint cluster-size-2,hpc

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

- cluster-size: Since clusters can be reused, you can decide to only use a cluster of exactly the right size. Created cluster will have a feature cluster-size-x. You can set the constraint cluster-size-x to make sure this matches and avoid having a 1 node job using a 16 nodes cluster. You do not need to set this feature if you don't mind having small jobs running on large clusters.  

- Instance Type: You can specify the OCI instance type that you’d like to run on as a constraint. This will make sure that you run on the right shape and also generate the right cluster. Instance types are defined in the `/opt/oci-hpc/autoscaling/queues.conf` file in yml format. Leave all of the field in there even if they are not used. You can define multiple queues and multiple instance type in each queue. If you do not select an instance type when creating your job, it will use the default one.

## Clusters folders: 
```
/opt/oci-hpc/autoscaling/clusters/clustername
```

## Logs: 
```
/opt/oci-hpc/autoscaling/logs
```

Each cluster will have his own log with name: `create_clustername_date.log` and `delete_clustername_date.log`
The log of the crontab will be in `crontab_slurm.log`


## Manual clusters: 
You can create and delete your clusters manually. 
### Cluster Creation
```
/opt/oci-hpc/autoscaling/create_cluster.sh NodeNumber clustername instance_type queue_name
```
Example: 
```
/opt/oci-hpc/autoscaling/create_cluster.sh 4 compute2-1-hpc HPC_instance compute2
```
The name of the cluster must be
queueName-clusterNumber-instanceType_keyword

The keyword will need to match the one from /opt/oci-hpc/autoscaling/queues.conf to be regirstered in Slurm

### Cluster Deletion: 
```
/opt/oci-hpc/autoscaling/delete_cluster.sh clustername
```

In case something goes wrong during the deletion, you can force the deletion with 
```
/opt/oci-hpc/autoscaling/delete_cluster.sh clustername FORCE
```
When the cluster is already being destroyed, it will have a file `/opt/oci-hpc/autoscaling/clusters/clustername/currently_destroying` 

## Autoscaling Monitoring
If you selected the autoscaling monitoring, you can see what nodes are spinning up and down as well as running and queued jobs. Everything will run automatically except the import of the Dashboard in Grafana due to a problem in the Grafana API. 

To do it manually, in your browser of choice, navigate to bastionIP:3000. Username and password are admin/admin, you can change those during your first login. Click on the + sign on the left menu bar and select import. Click on Upload JSON file and upload the file the is located at `/opt/oci-hpc/playbooks/roles/autoscaling_mon/files/dashboard.json`. Select autoscaling (MySQL) as your datasource. 

You will now see the dashboard. 


# LDAP 
If selected bastion host will act as an LDAP server for the cluster. It's strongly recommended to leave default, shared home directory. 
User management can be performed from the bastion using ``` cluster ``` command. 

