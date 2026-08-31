# Stack Usage

## Resizing

> [!IMPORTANT]
> If you are using GB200 or GB300 hosts, see special notes in [GraceBlackwell-based-shapes.md](GraceBlackwell-based-shapes.md).

The `mgmt` tool is deployed on the controller node as part of the HPC Cluster Stack deployment. Its full command reference is available [here](mgmt-cli.md).

### Adding nodes

Examples:

* Adding one node:
```
mgmt clusters add node --count 1
```
* Adding three nodes to cluster compute-1-hpc:
```
mgmt clusters add node --count 3 --cluster compute-1-hpc
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

* Building and installing Lustre on compute nodes after updating the cluster inventory with `add_lfs=true` and the `lfs_*` settings:
```
mgmt nodes reconfigure --action install-lfs --fields role=compute
```

* Building and installing Lustre on login nodes:
```
mgmt nodes reconfigure --action install-lfs --fields role=login
```

* Checking the cluster inventory before a one-time DGXC benchmarking install:
```
source /config/bin/setup_environment.sh
cluster_name=$(curl -fsL -H "Authorization: Bearer Oracle" \
  http://169.254.169.254/opc/v2/instance/freeformTags/cluster_name)
inventory="/config/playbooks/inventory_${cluster_name}"

$VENV_PATH/bin/ansible-inventory -i "$inventory" --graph
```

* Installing DGXC benchmarking shared components once on one GPU inventory host:
```
/config/bin/custom_ansible.sh dgxc_benchmarking \
  -e dgxc_target_hosts=<gpu-inventory-hostname> \
  -e dgxc_run_llmb_install=true
```

* Adding DGXC shell integration to existing compute nodes:
```
mgmt nodes reconfigure --action ansible --playbook dgxc_benchmarking_nodes --fields role=compute
```

Lustre notes:
- `install-lfs` uses the inventory-backed `lfs_target_path`, `lfs_source_IP`, `lfs_source_path`, and `lfs_options` values. Update inventory first, then run the command.
- Monitoring nodes are not supported targets for `install-lfs`.
- Lustre package builds coordinate through a shared lock under `/config/3rdparty/<arch>/lustre_pkg/builds`. If a builder crashes and leaves a stale lock behind, remove the matching lock directory manually and rerun the command.

DGXC notes:
- `dgxc_benchmarking=true` and `pyxis=true` enable DGXC shell integration during normal controller, login, monitoring, and compute node configuration.
- `playbooks/dgxc_benchmarking.yml` must target exactly one host because it writes to shared DGXC paths under `/config/3rdparty`.
- The DGXC shared install should target a GPU node, not the controller. If the target GPU node is not present in the Ansible inventory, SSH to the GPU node and run the same playbook locally without `dgxc_target_hosts`.
- `playbooks/dgxc_benchmarking.yml` replays the generated DGXC config when `dgxc_run_llmb_install=true`.
- `playbooks/dgxc_benchmarking_nodes.yml` installs `/opt/dgxc-benchmarking/bin` wrappers and the `load-dgxc-env` loader only.
- DGXC shell integration does not add DGXC commands to the default system `PATH` and does not install `git`, `git-lfs`, or other packages on every node.
- Source `/opt/dgxc-benchmarking/bin/load-dgxc-env` to add DGXC commands to an interactive shell.
- The same shell integration is also part of the standard controller, login, monitoring, and compute node playbooks so future nodes receive it during normal configuration when `dgxc_benchmarking=true`.
- Live `llmb-install` playback output is written to `/config/3rdparty/dgxc-benchmarking/logs/llmb-install-<node>.latest.log`.

[Local Disk Recovery](LocaldiskRecovery.md)

## Submitting jobs

Slurm job examples (NCCL allreduce) can be found for several GPU shapes: 
* [A100, H100, H200 and B200](/samples/gpu/nccl_run_allreduce.sbatch)
* [GB200 and GB300](/samples/gpu/nccl_run_allreduce_GB.sbatch)
* [MI300X](/samples/gpu/rccl_run_allreduce.sbatch)

## Logs

The infrastructure logs are stored in:
```
/config/logs
```

Each cluster has its own log file with named `create_clustername_date.log` and `delete_clustername_date.log` for its creation and deletion processes. The logs of the crontab is stored in `crontab_slurm.log`.
