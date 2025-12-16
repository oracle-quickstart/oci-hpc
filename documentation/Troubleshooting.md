# Troubleshooting

The cluster state and activity is logged in different files.

## Where are my logs?

### slurm (jobs) logs

The slurm job logs are created in the folder from which the job is launched. Its generic name is `slurm-jobid.out`.

### cluster logs

The cluster logs (creation, resizing, deletion) are stored in the `/config/logs` folder.

## Healthchecks

### In-node healthcheck

```
sudo python3 /opt/oci-hpc/healthchecks/check_gpu_setup.py
```


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
