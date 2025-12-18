# Troubleshooting

The cluster state and activity is logged in different files.

## Where are my logs?

### Initial configuration logs

The initial configuration of the controller will be available in the Terraform output as well as in `/config/logs/initial_configure.log`

If it succeeds, and the command `mgmt nodes list` does not return anything, check that the policy. If the pre-requisite are not met, you will see compute odes not renamed in the OCI console. 

### mgmt logs

The logs from the mgmt service (responsible for adding nodes to the DB, addig the nodes in Slurm topology,...) are stored in `/config/logs/mgmt.log`

### Compute nodes logs

Each node will configure itself. It's running the cloud-init script. A copy is available at `/config/bin/cloud-init.sh`
If the role of the node is compute, it will run /config/bin/copute.sh which will run the compute.yml ansible playbook. 
If the role of the node is login, it will run /config/bin/login.sh which will run the login.yml ansible playbook. 

The logs from the compute nodes are stored in `/config/logs/${hostame}.log`

### slurm (jobs) logs

The slurm job logs are created in the folder from which the job is launched. Its generic name is `slurm-jobid.out`.


## Healthchecks

### Passive healthchecks

To check if the RDMA interfaces and the GPUs are healthy, run the following command on any compute node:
This can run even on busy nodes as it does not use any resources.
```
sudo python3 /opt/oci-hpc/healthchecks/check_gpu_setup.py
```
This is automatically run in the prolog of ay job as well as idle/drained nodes every 5 minutes. (HealthCheckInterval in SLurm.conf)

### Active healthchecks

To run the active healthchecks, run the following command 
```
sudo python3 /opt/oci-hpc/healthchecks/active_healthcheck.py
```

Or run from the controller and replace the hostame by the node you would like to run this on:

```
sbatch -N 1 -w hostname /opt/oci-hpc/healthchecks/active_HC.sbatch
```

This is also run once every day on idle nodes in a low priority partition. (`compute_healthcheck`)

The output while runing on a node is at `/var/log/healthchecks/latest_active_healthcheck.log` on the. node or at 
`mgmt nodes get hostame` on the controller. 

### Active healthchecks

To run the active multi-ode healthchecks, submit this job and replace the hostame by the node you would like to run this on: (one or 2 nodes can be specified in the -w command)

```
sbatch -N 2 -w hostname /opt/oci-hpc/healthchecks/multi_node_active_HC.sbatch
```

This is also run once every day on idle nodes in a low priority partition. (`compute_healthcheck`)

The output while runing on a node is at `/var/log/healthchecks/latest_multi_node_active_healthcheck.log` on the nodes or at 
`mgmt nodes get hostame` on the controller. 

### Slurm reservation
During the initial setup of the nodes, a reservation (InitialValidation) is created to ensure that the nodes are not used by other jobs. You can check the reservation with the following command:
```
scontrol show reservation InitialValidation
```

Nodes can be removed from the reservation or the reservation can de removed if anything does not go as expected. 
Nodes that have a active Healthcheck but no multi-node healthcheck will be removed from the reservation after 10 minutes to avoid single nodes to be kept unavailable for too long. 

# Useful Information

## Cloud Services Used

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

## Meshpinger

Meshpinger is a tool for validating network layer connectivity between RDMA NICs on a cluster network in OCI. The tool is capable of initiating ICMP ping from every RDMA NIC port on the cluster network to every other RDMA NIC port on the same cluster network and reporting back the success/failure status of the pings performed in the form of logs.

Running the tool before starting workload on a cluster network should serve as a good precheck step to gain confidence on the network reachability between RDMA NICs. Typical causes for reachability failures that the tool can help pinpoint are:
1. Link down on the RDMA NIC
2. RDMA interface initialization or configuration issues including IP address assignment to the interface
3. Insufficient ARP table size on the node to store all needed peer mac addresses
