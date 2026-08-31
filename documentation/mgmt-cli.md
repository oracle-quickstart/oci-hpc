
# Cluster Management CLI (mgmt) Documentation

## Overview

CLI Utility for managing your cluster.

```bash
Usage: mgmt [OPTIONS] COMMAND [ARGS]...
```

## Root Options

- `--config FILE` - Path to config file (INI). Can also be set via `MGMT_CONFIG`
- `--debug / --no-debug` - Enable debug log output
- `--clush-parallel-executions INTEGER` - Number of parallel `clush` executions
- `--active-healthchecks / --no-active-healthchecks` - Enable or disable active healthchecks
- `--active-healthchecks-frequency INTEGER` - Active healthchecks frequency in hours
- `--multi-nodes-healthchecks / --no-multi-nodes-healthchecks` - Enable or disable multi-node healthchecks
- `--multi-nodes-healthchecks-frequency INTEGER` - Multi-node healthchecks frequency in hours
- `--manage-hosts / --no-manage-hosts` - Update `/etc/hosts` across nodes from database data

## Main Commands

- `clusters` - Commands to manage clusters
- `configurations` - Commands to manage configurations
- `database` - Commands to do in the database
- `fabrics` - Commands to display fabrics
- `images` - Commands to manage images
- `login` - Commands to manage login nodes
- `network` - Network block commands
- `nodes` - Commands to manage nodes
- `recommendations` - Commands to show recommendations about the cluster
- `services` - Commands to manage services
- `status` - Display an overview status of the OCI-HPC Stack

---

## clusters

Commands to manage clusters.

```bash
Usage: mgmt clusters [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `add` - Add nodes to clusters or memory fabrics
- `create` - Create a new cluster
- `delete` - Delete a cluster with name
- `list` - List all clusters in tabular or JSON format
- `update-instance-config` - Update an instance configuration for a cluster or GPU memory cluster

### clusters create

Create a new cluster.

```bash
Usage: mgmt clusters create [OPTIONS]
```

**Options:**
- `--count INTEGER` - Number of nodes to add; omit or use 0 with `--all` or multiple fabrics to use each fabric AVAILABLE count
- `--cluster TEXT` - Specify the name of the cluster [required]
- `--instancetype TEXT` - Specify the instance type of the cluster [required]
- `--names TEXT` - Comma separated list of host names
- `--fabric TEXT` - OCID of the memory fabric, or comma-separated OCIDs of memory fabrics for GMF based nodes
- `--all` - Use all unused GPU memory fabrics that have AVAILABLE hosts
- `--compute-local-block-id TEXT` - Use all unused GPU memory fabrics in this compute local block
- `--compute-network-block-id TEXT` - Use all unused GPU memory fabrics in this compute network block
- `--compute-hpc-island-id TEXT` - Use all unused GPU memory fabrics in this compute HPC island
- `--memorycluster TEXT` - Name used for the memory cluster fabric, default will be cluster_xxxxx with xxxxx the last 5 character of the fabric ocid
- `--targetsize INTEGER` - Target size for the memory cluster scale config, use 0 to deactivate
- `--minimum-gmc-size INTEGER` - Only use GPU memory fabrics with at least this many `AVAILABLE` hosts

**Examples:**

```bash
# Create a standard compute cluster
mgmt clusters create --count 3 --cluster mycluster --instancetype BM.Standard.E3.128

# Create a GPU cluster with memory fabric
mgmt clusters create --count 2 --cluster mycluster --instancetype BM.GPU.GB200.4 --fabric ocid1.fabric.oc1..xxxx --targetsize 18 --names node01,node02

# Create a GPU cluster across every unused available GPU memory fabric
mgmt clusters create --cluster mycluster --instancetype BM.GPU.GB300.4 --all --targetsize 18

# Create a GPU cluster across unused GPU memory fabrics with at least 12 available hosts
mgmt clusters create --cluster mycluster --instancetype BM.GPU.GB300.4 --all --minimum-gmc-size 12 --targetsize 18

# Create a GPU cluster across selected GPU memory fabrics
mgmt clusters create --count 18 --cluster mycluster --instancetype BM.GPU.GB300.4 --fabric ocid1.fabric.oc1..aaaa,ocid1.fabric.oc1..bbbb --targetsize 18

# Create a GPU cluster across every unused available GPU memory fabric in a compute local block
mgmt clusters create --cluster mycluster --instancetype BM.GPU.GB300.4 --compute-local-block-id ocid1.computelocalblock.oc1..aaaa --targetsize 18
```

### clusters add node

Add compute nodes to a cluster.

```bash
Usage: mgmt clusters add node [OPTIONS]
```

**Options:**
- `--count INTEGER` - Number of nodes to add [required]
- `--cluster TEXT` - Name of the cluster
- `--names TEXT` - Comma-separated list of host names
- `--memorycluster TEXT` - OCID of the GPU memory cluster (alternative to --cluster)

**Example:**

```bash
mgmt clusters add node --count 2 --cluster mycluster
# or resize a GPU memory cluster directly
mgmt clusters add node --count 2 --memorycluster ocid1.computegpumemorycluster.oc1..example
```

### clusters add memory-fabric

Add nodes to a memory fabric.

```bash
Usage: mgmt clusters add memory-fabric [OPTIONS]
```

**Options:**
- `--count INTEGER` - Number of nodes to add per memory fabric; omit or use 0 with `--all` or multiple fabrics to use each fabric AVAILABLE count
- `--cluster TEXT` - Name of the compute cluster [required]
- `--fabric TEXT` - OCID of the memory fabric, or comma-separated OCIDs of memory fabrics
- `--all` - Add all unused GPU memory fabrics that have AVAILABLE hosts
- `--compute-local-block-id TEXT` - Add all unused GPU memory fabrics in this compute local block
- `--compute-network-block-id TEXT` - Add all unused GPU memory fabrics in this compute network block
- `--compute-hpc-island-id TEXT` - Add all unused GPU memory fabrics in this compute HPC island
- `--memorycluster TEXT` - Name for the memory cluster
- `--computeclusterocid TEXT` - OCID of the compute cluster when adding memory cluster to existing compute cluster
- `--instancetype TEXT` - Instance type for the nodes; uses one from the existing node if not specified
- `--targetsize INTEGER` - Target size for the memory cluster, default to 18 if tenancy is whitelisted, use 0 to deactivate
- `--minimum-gmc-size INTEGER` - Only use GPU memory fabrics with at least this many `AVAILABLE` hosts

**Example:**

```bash
mgmt clusters add memory-fabric --count 1 --cluster mycluster --fabric ocid1.fabric.oc1..xxxx --instancetype BM.GPU.GB200.4
mgmt clusters add memory-fabric --all --cluster mycluster --instancetype BM.GPU.GB300.4
mgmt clusters add memory-fabric --all --cluster mycluster --instancetype BM.GPU.GB300.4 --minimum-gmc-size 12
mgmt clusters add memory-fabric --count 18 --cluster mycluster --fabric ocid1.fabric.oc1..aaaa,ocid1.fabric.oc1..bbbb --instancetype BM.GPU.GB300.4
mgmt clusters add memory-fabric --cluster mycluster --compute-network-block-id ocid1.computenetworkblock.oc1..aaaa --instancetype BM.GPU.GB300.4
```

### clusters delete

Delete a cluster with name.

```bash
Usage: mgmt clusters delete [OPTIONS]
```

**Options:**
- `--cluster TEXT` - Specify the name of the cluster
- `--memory_cluster TEXT` - Specify the name of the Memory cluster (Compute cluster does not need to be specified)
- `--force-skip-recycle` - Set GPU memory fabric recycle level to SKIP_RECYCLE before deleting memory cluster(s)
- `--force-full-recycle` - Set GPU memory fabric recycle level to FULL_RECYCLE before deleting memory cluster(s)

### clusters list

List all clusters in tabular or JSON format.

```bash
Usage: mgmt clusters list [OPTIONS]
```

**Options:**
- `--format [tabular|json]` - Output format [default: tabular]

**Examples:**

```bash
# List all clusters
mgmt clusters list

# List all clusters in JSON format
mgmt clusters list --format json
```

### clusters update-instance-config

Update an instance configuration for a compute cluster or GPU memory cluster.

```bash
Usage: mgmt clusters update-instance-config [OPTIONS]
```

**Options:**

- `--cluster-name TEXT` - Cluster name from the management database
- `--memory-cluster TEXT` - GPU memory cluster OCID or name to update
- `--image-id TEXT` - New image OCID
- `--ssh-key TEXT` - Override SSH public key
- `--cloud-init TEXT` - Path to cloud-init file
- `--boot-volume-size INTEGER` - Override boot volume size in GB
- `--display-name TEXT` - New instance configuration display name
- `--instance-config-id TEXT` / `--instance-configuration-id TEXT` - Existing instance configuration OCID to attach instead of creating one
- `--bvr` - Replace boot volumes on existing nodes
- `--bvr-size INTEGER` - New boot volume size in GB; requires `--bvr`

---

## configurations

Commands to manage configurations.

```bash
Usage: mgmt configurations [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `create` - Create Configuration
- `delete` - Delete Configuration
- `get` - Get information about the configuration
- `list` - List Configuration based on role, partition, or shape
- `update` - Update Configuration

### configurations create from-file

Create Configurations from file.

```bash
Usage: mgmt configurations create from-file [OPTIONS]
```

**Options:**
- `--file TEXT` - Name of the json or yaml file [required]

### configurations create from-existing

Duplicate Configuration with new name.

```bash
Usage: mgmt configurations create from-existing [OPTIONS]
```

**Options:**
- `--configuration TEXT` - Name of the existing configuration to copy [required]
- `--name TEXT` - Name for the new configuration [required]

### configurations delete

Delete Configuration.

```bash
Usage: mgmt configurations delete [OPTIONS]
```

**Options:**
- `--configuration TEXT` - Name of the configuration to delete [required]

### configurations get

Get information about the configuration.

```bash
Usage: mgmt configurations get [OPTIONS]
```

**Options:**
- `--name TEXT` - Get configuration name [required]

### configurations list

List Configuration based on role, partition, or shape.

```bash
Usage: mgmt configurations list [OPTIONS]
```

**Options:**
- `--format [tabular|json|yaml]` - Output format [default: tabular]
- `--output_file TEXT` - Name of the output file
- `--partition TEXT` - Get all configurations in that defined partition
- `--role [compute|login|all]` - Get all configurations for compute or login [default: all]
- `--shape TEXT` - Get all configurations with a particular shape

### configurations update

Update Configuration.

```bash
Usage: mgmt configurations update [OPTIONS]
```

**Options:**
- `--name TEXT` - Name of the configuration to update [required]
- `--fields TEXT` - Comma-separated list of updates to apply, Example: shape="VM.Standard.E5.Flex,instance_pool_ocpus=4" [required]

---

## database

Commands to do in the database.

```bash
Usage: mgmt database [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `add` - Add specific node to the DB
- `create` - Create database/tables
- `delete` - Delete nodes from the DB
- `export` - Export database contents to a SQLite DB file
- `fn-invoke` - Invoke the Oracle function for node launch/termination
- `scan-vcn` - Scan the specified VCN CIDR to list nodes
- `update` - Update a field for a list of nodes

### database add

Add specific node to the DB.

```bash
Usage: mgmt database add [OPTIONS]
```

**Options:**
- `--ip TEXT` - IP Address of the node [required]
- `--hostname TEXT` - Hostname of the node
- `--ocid TEXT` - OCID of the node

### database create

Create database/tables. Will not recreate tables that already exist.

```bash
Usage: mgmt database create [OPTIONS]
```

### database delete

Delete nodes from the DB. This will not terminate the nodes.

```bash
Usage: mgmt database delete [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)

### database export

Export database contents to a SQLite DB file. May not work if Python was built without sqlite support.

```bash
Usage: mgmt database export [OPTIONS]
```

**Options:**
- `--filename TEXT` - SQLite filename. Must not already exist [default: export.sqlite]
- `--use-base` - Use embedded Base metadata when creating target db. This can be used as very simple validation; if the source database schema doesn't match, an error may be raised

### database fn-invoke

Invoke the Oracle function for node launch/termination.

```bash
Usage: mgmt database fn-invoke [OPTIONS]
```

**Modes:**
- `--nodes TEXT` - Invoke for explicit nodes. The resolver first checks the mgmt DB, then tagged OCI instances by OCID, private IP, or display name/hostname.
- `--all` - Invoke the start event for all tagged OCI instances in the controller compartment that match `cluster_name` and `controller_name`.
- `--sync` - Compare tagged OCI instances and DB nodes. Replays start events for OCI nodes missing from the DB, and terminate events for DB nodes missing from OCI.

Exactly one of `--nodes`, `--all`, or `--sync` is required.

**Options:**
- `--function-id TEXT` - Oracle Functions function OCID. Defaults to `write_node_function_ocid` in `mgmt.ini`.
- `--event-type [start|terminate]` - Event type to send when using `--nodes` [default: start]. `terminate` is only valid with `--nodes`.
- `--workers INTEGER` - Maximum number of parallel function invocations [default: 10]

**Examples:**

```bash
# Replay a start event for one node, resolving from DB first and then OCI
mgmt database fn-invoke --nodes 172.16.7.61

# Replay a terminate event for a known DB node
mgmt database fn-invoke --nodes node1 --event-type terminate

# Replay start events for all tagged OCI nodes
mgmt database fn-invoke --all

# Reconcile missing start and terminate events between OCI and the DB
mgmt database fn-invoke --sync --workers 20
```

### database scan-vcn

Scan the specified VCN CIDR to list nodes.

```bash
Usage: mgmt database scan-vcn [OPTIONS] CIDR
```

**Options:**
- `--dns` - Scan DNS
- `--change_hostname` - Change OCI hostname

### database update

Update a field for a list of nodes.

```bash
Usage: mgmt database update [OPTIONS] IDENTIFIERS
```

**Options:**
- `--fields TEXT` - Add a list of update to do, Example shape=VM.Standard.E5.Flex,instance_pool_ocpus=4 [required]

---

## fabrics

Commands to display fabrics.

```bash
Usage: mgmt fabrics [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `list` - List all fabrics for nodes

### fabrics list

List all fabrics for nodes.

```bash
Usage: mgmt fabrics list [OPTIONS]
```

**Options:**
- `--full` - Get full information about the node
- `--rack-state [AVAILABLE|UNAVAILABLE|OCCUPIED]` - Only show fabrics with racks in this state
- `--filter [AVAILABLE|UNAVAILABLE|OCCUPIED]` - Alias for `--rack-state`

---

## images

Commands to manage images.

```bash
Usage: mgmt images [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `add-shape` - Import image
- `create` - Import image
- `list` - List images in tabular, JSON, or YAML format

### images add-shape

Import image.

```bash
Usage: mgmt images add-shape [OPTIONS]
```

**Options:**
- `--image TEXT` - Image OCID or name of the image to modify [required]
- `--compartment TEXT` - Specify compartment OCID if not controller compartment
- `--shape TEXT` - Shape to add to the image [required]

### images create

Import image.

```bash
Usage: mgmt images create [OPTIONS]
```

**Options:**
- `--url TEXT` - URL of the image to import [required]
- `--compartment TEXT` - Specify compartment OCID if not controller compartment

### images list

List images.

```bash
Usage: mgmt images list [OPTIONS]
```

**Options:**
- `--format [tabular|json|yaml]` - Output format [default: tabular]
- `--used` - Only show currently used images [default: False]
- `--compartment TEXT` - Specify compartment OCID if not controller compartment

---

## login

Commands to manage login nodes.

```bash
Usage: mgmt login [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `create` - Add login node to the cluster
- `delete` - Delete a login node
- `list` - List all login nodes

### login create

Add login node to the cluster.

```bash
Usage: mgmt login create [OPTIONS]
```

**Options:**
- `--count INTEGER` - Number of login nodes to add [required]
- `--configuration TEXT` - Specify the name of the login configuration [required]
- `--names TEXT` - Comma separated list of host names [required]

### login delete

Delete a login node.

```bash
Usage: mgmt login delete [OPTIONS]
```

**Options:**
- `--hostname TEXT` - Specify the name of the login node [required]

### login list

List all login nodes.

```bash
Usage: mgmt login list [OPTIONS]
```

**Options:**
- `--format [tabular|json]` - Output format [default: tabular]

---

## network

Network block commands.

```bash
Usage: mgmt network [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `blocks` - Commands to manage network blocks
- `rails` - Commands to manage rails

### network blocks list cluster

Get blocks by cluster.

```bash
Usage: mgmt network blocks list cluster [OPTIONS]
```

**Options:**
- `--cluster TEXT` - Name of the cluster [required]

### network rails list cluster

Get rails by cluster.

```bash
Usage: mgmt network rails list cluster [OPTIONS]
```

**Options:**
- `--cluster TEXT` - Name of the cluster [required]
- `--nodes / --no-nodes` - Show nodes in the rail

---

## nodes

Commands to manage nodes.

```bash
Usage: mgmt nodes [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `boot-volume-swap` - Boot Volume Swap one or more nodes
- `add-dns-entry` - Add or update a DNS A record for a single node or IP address
- `console-history` - Fetch console history for one or more nodes
- `delete-dns-entry` - Delete a DNS A record by hostname
- `get` - Get information about nodes
- `healthchecks` - Tag nodes as unhealthy
- `list` - List nodes with various filters and formats
- `reboot` - Reboot one or more nodes
- `reconfigure` - Rerun the cloud-init script on the nodes
- `tag` - Tag nodes as unhealthy
- `tag-and-terminate` - Tag and Terminate nodes
- `terminate` - Terminate nodes

### nodes boot-volume-swap

Boot Volume Swap one or more nodes.

```bash
Usage: mgmt nodes boot-volume-swap [OPTIONS]
```

You must specify either `--nodes` or `--fields` to identify which nodes to reboot.

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)
- `--image TEXT` - Specify the image for BVR
- `--size INTEGER` - Specify the size for BVR in GB

**Examples:**

```bash
# Boot Volume Swap by node names
mgmt nodes boot-volume-swap --nodes=node1,node2

# Boot Volume Swap by fields
mgmt nodes boot-volume-swap --fields=role=compute,status=running

# Boot Volume Swap image
mgmt nodes boot-volume-swap --nodes=node1 --image=ocid1.image.oc1..exampleuniqueid

# Boot Volume Swap BV size
mgmt nodes boot-volume-swap --nodes=node1 --size=100
```

### nodes add-dns-entry

Add or update a private DNS A record for exactly one node or IP address.

```bash
Usage: mgmt nodes add-dns-entry [OPTIONS]
```

**Options:**

- `--nodes TEXT` - One node identifier: IP address, hostname, OCID, serial, or OCI name
- `--ip TEXT` - IP address to use without a management database entry
- `--alternate_hostname TEXT` - Hostname to use for the DNS A record; required with `--ip`

Use exactly one of `--nodes` or `--ip`.

### nodes console-history

Get console history for nodes selected by identifiers or fields.

```bash
Usage: mgmt nodes console-history [OPTIONS]
```

**Options:**

- `--nodes TEXT` - Comma-separated node identifiers
- `--fields TEXT` - Fields to filter nodes, for example `role=compute,status=running`

Use exactly one of `--nodes` or `--fields`.

### nodes delete-dns-entry

Delete a private DNS A record by hostname.

```bash
Usage: mgmt nodes delete-dns-entry [OPTIONS]
```

**Options:**

- `--hostname TEXT` - Hostname to remove [required]
- `--cluster TEXT` - Cluster name used to select inventory DNS variables

### nodes get

Get information about nodes.

```bash
Usage: mgmt nodes get [OPTIONS] COMMAND [ARGS]...
```

**Subcommands:**
- `any` - Default: Get info by serial, IP, OCID, or hostname
- `ids` - Get information about a node by ID
- `ips` - Get information about a node by IP
- `names` - Get information about a node by host name
- `serials` - Get information about a node by serial number

**Common Options:**
- `--format [node|csv|json]` - Output format [default: node]

### nodes healthchecks

Get healthcheck details of node/s.

```bash
Usage: mgmt nodes healthchecks [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)
- `--type [all|passive|active|multi-node]` - Type of healthcheck to run (all, passive, active, multi-node)
- `--exclude-node TEXT` - Node to exclude from multi_node healthcheck
- `--reservation TEXT` - Include a Reservation Name for the healthcheck in case the nodes are in a reservation, InitialValidation is the reservation created for all new nodes

**Examples:**

```bash
# Get healthcheck details of a node
mgmt nodes healthchecks --nodes gpu-6175
```
### nodes list

List nodes with various filters and formats.

```bash
Usage: mgmt nodes list [OPTIONS]
```

**Options:**
- `--one-line` - Share the hostnames list in one line (or compact output with --json)
- `--cluster TEXT` - List nodes that are part of named cluster
- `--memory-cluster TEXT` - List nodes that are part of named memory cluster
- `--style [lines|box|none]` - Table style for tabular output [default: box]
- `--format [tabular|node|csv|json]` - Output format [default: tabular]
- `--width INTEGER` - Width of output [default: detect from terminal or COLUMNS env var]
- `--columns TEXT` - Comma separated list of fields to display. Also accepts ALL, DEFAULT, SIMPLE (all single-line fields), HC (all healthcheck fields + simple fields), or LIST (to list field names and exit)
- `--no-header` - Do not include header in tabular/csv formats
- `--fields TEXT` - Add a list of fields to filter, Example: role=compute,status=running

**Examples:**

```bash
# List all nodes in a cluster
mgmt nodes list --cluster mycluster

# Lists all node hostnames in a boxed table format without headers, using a fixed width of 30
mgmt nodes list --columns hostname --style box --no-header --width 30

# Lists all compute nodes in a json format with all fields
mgmt nodes list --format json --columns all --fields role=compute
```

### nodes reboot

Reboot one or more nodes.

```bash
Usage: mgmt nodes reboot [OPTIONS]
```

You must specify either `--nodes` or `--fields` to identify which nodes to reboot.

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)
- `--soft` - Perform a soft reboot (OS level) instead of a hard reset

**Examples:**

```bash
# Reboot by node names
mgmt nodes reboot --nodes=node1,node2

# Reboot by fields
mgmt nodes reboot --fields=role=compute,status=running

# Soft reboot
mgmt nodes reboot --nodes=node1 --soft
```

### nodes reconfigure

Rerun the cloud-init script on the nodes.

```bash
Usage: mgmt nodes reconfigure [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)
- `--action [compute|controller|all|custom|command|ansible|install-lfs|dr-hpc|slurm-reinit|metadata|localdisk-recover|localdisk-raid0|localdisk-raid10|enable-instance-rdma-plugins]` - What to reconfigure:
  - `compute` - Rerun the cloud-init
  - `controller` - Reconfigure the node on the controller (Slurm Topology and Prometheus targets)
  - `all` - Reconfigure the node on the controller and the cloud-init
  - `custom` - Run the `custom.yml` playbook on the selected nodes
  - `command` - Run a custom command on the nodes
  - `ansible` - Run a specific playbook on the selected nodes with `--playbook`
  - `install-lfs` - Build and install the Lustre client, then mount Lustre using inventory-backed `lfs_*` settings
  - `dr-hpc` - Install or update DR HPC on compute nodes; use `--version` to pin a version
  - `metadata` - Refresh metadata on selected nodes
  - `slurm-reinit` - Restart SLURM on selected nodes after clearing local SLURM state
  - `localdisk-recover` - Recover `/mnt/localdisk` on selected nodes
  - `localdisk-raid0` - Recreate `/mnt/localdisk` as RAID0
  - `localdisk-raid10` - Recreate `/mnt/localdisk` as RAID10
  - `enable-instance-rdma-plugins` - Enable the OCI Compute RDMA instance plugins (Compute HPC RDMA Authentication and Compute HPC RDMA Auto-Configuration) on selected nodes
- `--command TEXT` - Specify the command to run on the nodes. To be used with --action=command
- `--playbook TEXT` - Specify the playbook to run on the nodes. To be used with --action=ansible
- `--version TEXT` - DR HPC version to pin; use with `--action=dr-hpc`

**Lustre notes:**
- `install-lfs` requires `add_lfs=true` and valid `lfs_target_path`, `lfs_source_IP`, `lfs_source_path`, and `lfs_options` values in the cluster inventory before it is run.
- `install-lfs` is supported on controller, `slurm_backup`, login, and compute nodes. Monitoring nodes are explicitly rejected.
- The build uses a shared lock under `/config/3rdparty/<arch>/lustre_pkg/builds`. If a builder crashes and leaves a stale lock behind, remove the matching lock directory manually and rerun the command.

**DGXC notes:**
- DGXC playbooks require `dgxc_benchmarking=true` and `pyxis=true` in inventory.
- Use `playbooks/dgxc_benchmarking.yml` for the one-time shared DGXC install. It must target exactly one host because it writes to shared paths under `/config/3rdparty`.
- Use `playbooks/dgxc_benchmarking_nodes.yml` with `--action ansible` to install only `/opt/dgxc-benchmarking/bin` wrappers and the `load-dgxc-env` loader on selected nodes.
- DGXC shell integration does not add DGXC commands to the default system `PATH` and does not install `git`, `git-lfs`, or other packages on every node.
- Source `/opt/dgxc-benchmarking/bin/load-dgxc-env` to add DGXC commands to an interactive shell.
- The same shell integration is included in the standard controller, login, monitoring, and compute playbooks so future nodes receive it during normal configuration when `dgxc_benchmarking=true`.
- Live `llmb-install` playback output is written to `/config/3rdparty/dgxc-benchmarking/logs/llmb-install-<node>.latest.log`.

### nodes tag

Tag nodes as unhealthy.

```bash
Usage: mgmt nodes tag [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)

### nodes tag-and-terminate

Tag and Terminate nodes.

```bash
Usage: mgmt nodes tag-and-terminate [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)

### nodes terminate

Terminate nodes.

```bash
Usage: mgmt nodes terminate [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--fields TEXT` - Fields to filter nodes (e.g., role=compute,status=running)

---

## recommendations

Commands to show recommendations about the cluster.

```bash
Usage: mgmt recommendations [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `list` - List all the nodes with recommendations
- `run` - Run all the recommendations

### recommendations list

List all the nodes with recommendations.

```bash
Usage: mgmt recommendations list [OPTIONS]
```

**Options:**
- `--healthcheck` - Only show the Healthcheck Recommendations
- `--unreachable` - Only show the unreachable nodes
- `--unconfigured` - Only show the nodes failing to start
- `--unreachable_timeout INTEGER` - Timeout in minutes before a node is considered unreachable
- `--unconfigured_timeout INTEGER` - Timeout in minutes before a node is considered unreachable

### recommendations run

Run all the recommendations.

```bash
Usage: mgmt recommendations run [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Comma separated list of nodes (IP Addresses, hostnames, OCID's, serials or oci names)
- `--healthcheck`
- `--unreachable` - Get full information about the nodes
- `--unconfigured` - Get full information about the nodes
- `--unreachable_timeout INTEGER` - Timeout in minutes before a node is considered unreachable
- `--unconfigured_timeout INTEGER` - Timeout in minutes before a node is considered unreachable

---

## services

Commands to manage services.

```bash
Usage: mgmt services [OPTIONS] COMMAND [ARGS]...
```

### Subcommands

- `active-hc` - Run active healthcheck
- `all` - Run full workflow: scan queue, update metadata, run ansible and update nodes in case of success
- `ansible` - Run Ansible to configure nodes
- `init` - Reconfigure the Slurm Config files on the controller
- `multi-node-hc` - Run active healthcheck
- `scan-host-api` - Scan Host API, update Health information and report number of available nodes in the dedicated pool
- `scan-queue` - Scan queue for new or removed nodes and update the DB
- `update-metadata` - Update metadata for all hosts in the DB

### services active-hc

Run active healthcheck.

```bash
Usage: mgmt services active-hc [OPTIONS]
```

### services all

Run full workflow: scan queue, update metadata, run ansible and update nodes in case of success.

```bash
Usage: mgmt services all [OPTIONS]
```

**Options:**
- `--http_port INTEGER` - Specify HTTP Port

Node auto-add is configured in `/config/mgmt/auto_add_nodes.json`. Each HPC island maps to one cluster. Standard GPU shapes may use the compact shape list. GB shapes require per-shape settings with `minimum_available_nodes`; a new GMC is created only for an unused GPU memory fabric whose lifecycle state is `AVAILABLE`, whose available hosts all match the configured shape, and whose available host count meets the threshold. `target_size` is optional and defaults to the number of hosts launched from that fabric.

```json
{
  "enabled": true,
  "hpc_islands": {
    "ocid1.hpcisland...": {
      "cluster": "example-cluster",
      "shapes": {
        "BM.GPU.GB300.4": {
          "minimum_available_nodes": 18,
          "target_size": 18
        }
      }
    }
  }
}
```

### services ansible

Run Ansible to configure nodes.

```bash
Usage: mgmt services ansible [OPTIONS]
```

### services init

Reconcile the Slurm config files on the controller.

```bash
Usage: mgmt services init [OPTIONS]
```

### services multi-node-hc

Run active healthcheck.

```bash
Usage: mgmt services multi-node-hc [OPTIONS]
```

### services scan-host-api

Scan Host API, update Health information and report number of available nodes in the dedicated pool.

```bash
Usage: mgmt services scan-host-api [OPTIONS]
```

### services scan-queue

Scan queue for new or removed nodes and update the DB.

```bash
Usage: mgmt services scan-queue [OPTIONS]
```

### services update-metadata

Update metadata for all hosts in the DB.

```bash
Usage: mgmt services update-metadata [OPTIONS]
```

**Options:**
- `--nodes TEXT` - Any of the hostname, OCID, IP, serial, OCI_name of the node
- `--http_port INTEGER` - Specify HTTP Port

---

## status

Display an overview status of the OCI-HPC Stack.

```bash
Usage: mgmt status [OPTIONS]
```

By default the command runs once and prints the status in color.

**Options:**
- `--no_color` - Disable color output
