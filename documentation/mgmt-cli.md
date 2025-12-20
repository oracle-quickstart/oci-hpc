
# Cluster Management CLI (mgmt) Documentation

## Overview

CLI Utility for managing your cluster.

```bash
Usage: mgmt [OPTIONS] COMMAND [ARGS]...
```

## Main Commands

- `clusters` - Commands to manage clusters
- `configurations` - Commands to manage configurations
- `database` - Commands to do in the database
- `fabrics` - Commands to display fabrics
- `login` - Commands to manage login nodes
- `network` - Network block commands
- `nodes` - Commands to manage nodes
- `recommendations` - Commands to show recommendations about the cluster
- `services` - Commands to manage services

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

### clusters create

Create a new cluster.

```bash
Usage: mgmt clusters create [OPTIONS]
```

**Options:**
- `--count INTEGER` - Number of nodes to add [required]
- `--cluster TEXT` - Specify the name of the cluster [required]
- `--instancetype TEXT` - Specify the instance type of the cluster [required]
- `--names TEXT` - Comma separated list of host names
- `--fabric TEXT` - OCID of the memory fabric to add the nodes in for BM.GPU.GB200.4 nodes
- `--memorycluster TEXT` - Name used for the memory cluster fabric, default will be cluster_xxxxx with xxxxx the last 5 character of the fabric ocid

**Examples:**

```bash
# Create a standard compute cluster
mgmt clusters create --count 3 --cluster mycluster --instancetype BM.Standard.E3.128

# Create a GPU cluster with memory fabric
mgmt clusters create --count 2 --cluster mycluster --instancetype BM.GPU.GB200.4 --fabric ocid1.fabric.oc1..xxxx --names node01,node02
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
- `--memorycluster TEXT` - Name of the memory cluster (alternative to --cluster)

**Example:**

```bash
mgmt clusters add node --count 2 --cluster mycluster
```

### clusters add memory-fabric

Add nodes to a memory fabric.

```bash
Usage: mgmt clusters add memory-fabric [OPTIONS]
```

**Options:**
- `--count INTEGER` - Number of nodes to add [required]
- `--cluster TEXT` - Name of the compute cluster [required]
- `--fabric TEXT` - OCID of the memory fabric [required]
- `--memorycluster TEXT` - Name for the memory cluster
- `--instancetype TEXT` - Instance type for the nodes [required]

**Example:**

```bash
mgmt clusters add memory-fabric --count 1 --cluster mycluster --fabric ocid1.fabric.oc1..xxxx --instancetype BM.GPU.GB200.4
```

### clusters delete

Delete a cluster with name.

```bash
Usage: mgmt clusters delete [OPTIONS]
```

**Options:**
- `--cluster TEXT` - Specify the name of the cluster
- `--memory_cluster TEXT` - Specify the name of the Memory cluster (Compute cluster does not need to be specified)

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
- `--action [compute|controller|all|custom|command]` - What to reconfigure:
  - `compute` - Rerun the cloud-init
  - `controller` - Reconfigure the node on the controller (Slurm Topology and Prometheus targets)
  - `all` - Reconfigure the node on the controller and the cloud-init
  - `custom` - Reconfigure the node on the controller and the cloud-init
  - `command` - Run a custom command on the nodes
- `--command TEXT` - Specify the command to run on the nodes. To be used with --action=command

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

### services ansible

Run Ansible to configure nodes.

```bash
Usage: mgmt services ansible [OPTIONS]
```

### services init

Reconfigure the Slurm Config files on the controller. topology.conf.

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

