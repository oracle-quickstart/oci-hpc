# Stack Usage

## Resizing

> [!IMPORTANT]
> If you are using GB200 or GB300 hosts, see special notes in [GraceBlackwell-based-shapes.md](GraceBlackwell-based-shapes.md).

The `mgmt` tool is deployed on the controller node as part of the HPC Cluster Stack deployment. The full mgmt command help is available [here](documentation/mgmt-help.txt). 

### Adding nodes

Examples:

* Adding one node:
```
mgmt clusters add node --count 1
```
* Adding three nodes to cluster compute-1-hpc:
```
mgmt clusters add add-node --count 3 --cluster compute-1-hpc
```

### Removing nodes

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
* Removing a list of nodes (clustershell notation):  
```
mgmt nodes terminate --nodes GPU-[123,456]
```

### Reconfiguring nodes

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

## Submiting jobs

Slurm job examples (NCCL allreduce) can be found for several GPU shapes: 
* [A100, H100, H200 and B200](samples/gpu/nccl_run_allreduce.sbatch)
* [GB200 and GB300](samples/gpu/nccl_run_allreduce_GB200.sbatch)
* [MI300X](samples/gpu/nccl_run_allreduce.sbatch)

## Logs

The infrastructure logs are stored in:
```
/config/logs
```

Each cluster has its own log file with named `create_clustername_date.log` and `delete_clustername_date.log` for its creation and deletion processes. The logs of the crontab is stored in `crontab_slurm.log`.