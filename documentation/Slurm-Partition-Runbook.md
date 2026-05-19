# Runbook: Create a New Slurm Partition and Add GPU Nodes

## Goal

Create a new Slurm partition, sync the Slurm configuration safely, and then create a new OCI-backed cluster that places nodes into that partition. Run all commands below from the Slurm controller node.

## Important Notes

- The `mgmt clusters create --instancetype ...` option expects a **mgmt configuration name**, not a raw OCI shape.
- In this runbook, the new mgmt configuration name and Slurm partition name are kept the same for simplicity.
- A healthcheck partition named `${PARTITION_NAME}-healthcheck` will be created automatically. This is expected.
- Do not submit user jobs to the `*-healthcheck` partition.
- The image used below must already be a valid **GPU-ready image** with the required drivers and packages for your selected shape.
- The `RDMA_ENABLED` value should match the requirements of the GPU shape and network design you are deploying.

## Values Used In This Runbook

```bash
# Name of the new mgmt configuration
CONFIG_NAME="gpu-compute"

# Name of the new Slurm partition
PARTITION_NAME="gpu-compute"

# Name of the new OCI cluster to create
CLUSTER_NAME="gpu-cluster"

# Number of nodes to create initially
NODE_COUNT="2"

# OCI shape for the new GPU nodes
# For supported shapes, see:
# https://docs.oracle.com/en-us/iaas/Content/Compute/References/computeshapes.htm
GPU_SHAPE="BM.GPU.<replace-me>"

# Whether RDMA should be enabled for this shape and deployment
RDMA_ENABLED="true"

# GPU-compatible image OCID
GPU_IMAGE_OCID="ocid1.image.<replace-me>"
```

## Step 1: Create a New Configuration

Clone the existing `default` compute configuration into a new configuration.

```bash
# Create a new mgmt configuration by cloning the current default compute config
mgmt configurations create from-existing --configuration default --name "${CONFIG_NAME}"
```

## Step 2: Convert the New Configuration Into a GPU Partition Config

Update the cloned configuration so it points to:

- the new partition name
- the target GPU shape
- the RDMA setting required for that shape
- the target image

```bash
# Update the cloned configuration so it targets the selected GPU nodes and belongs to the new Slurm partition.
mgmt configurations update \
  --name "${CONFIG_NAME}" \
  --fields "partition=${PARTITION_NAME},default_partition=false,shape=${GPU_SHAPE},rdma_enabled=${RDMA_ENABLED},image_id=${GPU_IMAGE_OCID}"
```

## Step 3: Verify the New Configuration

Before changing Slurm, confirm the configuration looks correct.

```bash
# Inspect the new configuration
mgmt configurations get --name "${CONFIG_NAME}"
```

Verify these fields carefully in the output:

- `name = <your CONFIG_NAME>`
- `partition = <your PARTITION_NAME>`
- `default_partition = False`
- `shape = <your GPU_SHAPE>`
- `rdma_enabled = <your RDMA_ENABLED>`
- `image_id = <your GPU_IMAGE_OCID>`

## Step 4: Preview the Slurm Changes

Run a dry-run first so the team can review the generated Slurm updates safely.

```bash
# Preview the managed slurm.conf changes without applying them
sudo mgmt configurations update-slurm --dry-run
```

## Step 5: Apply the Slurm Changes

If the dry-run looks correct, apply the configuration to Slurm.

```bash
# Apply the new managed Slurm configuration
sudo mgmt configurations update-slurm
```

Notes:

- This updates the managed `Nodeset`, `NodeName`, and `PartitionName` entries.
- It also runs `scontrol reconfigure`.
- The tool creates backup files for the managed Slurm config files.

## Step 6: Verify the New Partition Exists

```bash
# Verify the main partition exists
scontrol show partition "${PARTITION_NAME}"

# Verify the auto-generated healthcheck partition exists
scontrol show partition "${PARTITION_NAME}-healthcheck"

# Confirm the partition appears in sinfo output
sinfo
```

Expected result:

- `${PARTITION_NAME}` should exist as a normal partition
- `${PARTITION_NAME}-healthcheck` should exist as the healthcheck partition

## Step 7: Create the New GPU Cluster

Create the initial set of GPU nodes using the new mgmt configuration name.

```bash
# Create a new OCI-backed cluster using the mgmt configuration name
mgmt clusters create \
  --cluster "${CLUSTER_NAME}" \
  --count "${NODE_COUNT}" \
  --instancetype "${CONFIG_NAME}"
```

## Step 8: Watch the Nodes Register

```bash
# Watch the newly created nodes as they register and get configured
mgmt nodes list \
  --fields "cluster_name=${CLUSTER_NAME}" \
  --columns hostname,status,compute_status,controller_status,slurm_partition,shape

# Confirm the nodes appear in Slurm
sinfo
```

## Step 9: Add More Nodes Later

Once the new cluster exists, you can scale it out with `mgmt clusters add node`.

```bash
# Add 2 more nodes to the same GPU cluster later
mgmt clusters add node --cluster "${CLUSTER_NAME}" --count 2
```

## Quick Copy/Paste Version

```bash
CONFIG_NAME="gpu-compute"
PARTITION_NAME="gpu-compute"
CLUSTER_NAME="gpu-cluster"
NODE_COUNT="2"
GPU_SHAPE="BM.GPU.<replace-me>"
RDMA_ENABLED="true"
GPU_IMAGE_OCID="ocid1.image.<replace-me>"

mgmt configurations create from-existing --configuration default --name "${CONFIG_NAME}"

mgmt configurations update \
  --name "${CONFIG_NAME}" \
  --fields "partition=${PARTITION_NAME},default_partition=false,shape=${GPU_SHAPE},rdma_enabled=${RDMA_ENABLED},image_id=${GPU_IMAGE_OCID}"

mgmt configurations get --name "${CONFIG_NAME}"

sudo mgmt configurations update-slurm --dry-run

sudo mgmt configurations update-slurm

scontrol show partition "${PARTITION_NAME}"

scontrol show partition "${PARTITION_NAME}-healthcheck"

sinfo

mgmt clusters create \
  --cluster "${CLUSTER_NAME}" \
  --count "${NODE_COUNT}" \
  --instancetype "${CONFIG_NAME}"

mgmt nodes list \
  --fields "cluster_name=${CLUSTER_NAME}" \
  --columns hostname,status,compute_status,controller_status,slurm_partition,shape

sinfo
```

## Appendix: GPU Cluster Operations Cheat Sheet

This is a quick reference for adding and removing nodes from the GPU Slurm setup using the `mgmt` utility.

Current assumptions:

- Slurm partition: `gpu-compute`
- `mgmt` configuration name: `gpu-compute`
- OCI / mgmt cluster name: `gpu-cluster`
- Shape: `BM.GPU.<replace-me>`

Important notes:

- `mgmt clusters add node` works by `cluster` name, not by Slurm partition name.
- `mgmt nodes terminate` works best with either:
- `--nodes` for exact hostnames, or
- `--fields "role=compute,cluster_name=gpu-cluster"` for cluster-wide actions
- Avoid using `--fields "slurm_partition=gpu-compute"` for deletes. In this codebase, `slurm_partition` is stored as a combined value and may include the healthcheck partition as well.

## 1. Verify Current State

```bash
# List clusters known to mgmt
mgmt clusters list

# List nodes that currently belong to the GPU cluster
mgmt nodes list \
  --cluster gpu-cluster \
  --columns hostname,status,shape,cluster_name,slurm_partition

# Verify the Slurm partition state
sinfo -p gpu-compute
```

## 2. Add Nodes to the GPU Cluster

```bash
# Add 1 node to the existing GPU cluster
mgmt clusters add node --cluster gpu-cluster --count 1
```

```bash
# Add 2 nodes to the existing GPU cluster
mgmt clusters add node --cluster gpu-cluster --count 2
```

## 3. Remove Specific Nodes from the GPU Cluster

Use this when you want to remove only selected nodes.

```bash
# Remove two specific nodes by hostname
mgmt nodes terminate --nodes gpu-7001,gpu-7002
```

```bash
# Remove a set of nodes using ClusterShell / NodeSet notation
mgmt nodes terminate --nodes gpu-[7001,7002]
```

You can also identify nodes first, then remove them:

```bash
# Inspect current nodes before terminating any
mgmt nodes list \
  --cluster gpu-cluster \
  --columns hostname,status,shape,cluster_name,slurm_partition
```

## 4. Remove All Compute Nodes from the GPU Cluster

Use this when you want to scale the cluster down to zero nodes but keep the cluster definition.

Important: this section and Section 5 are alternative actions, not sequential steps. If you want to remove the full cluster object, use `mgmt clusters delete --cluster gpu-cluster` directly instead of first terminating all cluster nodes individually.

```bash
# Terminate all compute nodes that belong to gpu-cluster
mgmt nodes terminate --fields "role=compute,cluster_name=gpu-cluster"
```

This is safer than filtering on `slurm_partition`, because the code matches field values exactly and the stored Slurm partition string may include both:

- `gpu-compute`
- `gpu-compute-healthcheck`

## 5. Delete the Entire GPU Cluster

Use this only if you want to remove the full cluster object, not just some nodes. This is an alternative to Section 4, not a follow-on step after scaling the cluster down to zero.

```bash
# Delete the entire GPU cluster and its nodes
mgmt clusters delete --cluster gpu-cluster
```

This is different from `mgmt nodes terminate`:

- `mgmt nodes terminate` removes selected instances
- `mgmt clusters delete --cluster ...` removes the whole cluster construct

## 6. Reconcile and Refresh State

After add or delete operations, run the controller workflow to refresh metadata and configuration state immediately.

```bash
# Run the full management workflow
mgmt services all
```

This performs the combined workflow that scans the queue, refreshes metadata, runs Ansible as needed, and updates node state.

## 7. Verify After the Change

```bash
# Check node records in mgmt
mgmt nodes list \
  --cluster gpu-cluster \
  --columns hostname,status,compute_status,controller_status,slurm_partition,shape

# Check Slurm partition state
sinfo -p gpu-compute
```

Optional detailed check:

```bash
# Show all node fields in JSON if deeper troubleshooting is needed
mgmt nodes list \
  --cluster gpu-cluster \
  --format json \
  --columns ALL
```

## 8. Most Common Commands

```bash
# Add 2 nodes
mgmt clusters add node --cluster gpu-cluster --count 2

# Remove two specific nodes
mgmt nodes terminate --nodes gpu-7001,gpu-7002

# Remove all compute nodes in the cluster
mgmt nodes terminate --fields "role=compute,cluster_name=gpu-cluster"

# Delete the entire cluster
mgmt clusters delete --cluster gpu-cluster

# Refresh mgmt/controller state
mgmt services all

# Verify Slurm
sinfo -p gpu-compute
```

```
---

## 3. Remove Specific Nodes from the GPU Cluster

Use this when you want to remove only selected nodes.

```bash

# Remove two specific nodes by hostname
mgmt nodes terminate --nodes gpu-7001,gpu-7002

```

```bash

# Remove a set of nodes using ClusterShell / NodeSet notation
mgmt nodes terminate --nodes gpu-[7001,7002]

```

You can also identify nodes first, then remove them:

```bash

# Inspect current nodes before terminating any
mgmt nodes list \
--cluster gpu-cluster \
--columns hostname,status,shape,cluster_name,slurm_partition

```
---

## 4. Remove All Compute Nodes from the GPU Cluster

Use this when you want to scale the cluster down to zero nodes but keep the cluster definition.

Important: this section and Section 5 are alternative actions, not sequential steps. If you want to remove the full cluster object, use `mgmt clusters delete --cluster gpu-cluster` directly instead of first terminating all cluster nodes individually.

```bash

# Terminate all compute nodes that belong to gpu-cluster
mgmt nodes terminate --fields "role=compute,cluster_name=gpu-cluster"

```

This is safer than filtering on `slurm_partition`, because the code matches field values exactly and the stored Slurm partition string may include both:

- `gpu-compute`
- `gpu-compute-healthcheck`
---

## 5. Delete the Entire GPU Cluster

Use this only if you want to remove the full cluster object, not just some nodes. This is an alternative to Section 4, not a follow-on step after scaling the cluster down to zero.

```bash

# Delete the entire GPU cluster and its nodes
mgmt clusters delete --cluster gpu-cluster

```

This is different from `mgmt nodes terminate`: 

- `mgmt nodes terminate` removes selected instances
- `mgmt clusters delete --cluster ...` removes the whole cluster construct
---

## 6. Reconcile and Refresh State

After add or delete operations, run the controller workflow to refresh metadata and configuration state immediately.

```bash

# Run the full management workflow
mgmt services all

```

This performs the combined workflow that scans the queue, refreshes metadata, runs Ansible as needed, and updates node state.

---

## 7. Verify After the Change

```bash

# Check node records in mgmt
mgmt nodes list \
--cluster gpu-cluster \
--columns hostname,status,compute_status,controller_status,slurm_partition,shape

# Check Slurm partition state
sinfo -p gpu-compute

```

Optional detailed check:

```bash

# Show all node fields in JSON if deeper troubleshooting is needed
mgmt nodes list \
--cluster gpu-cluster \
--format json \
--columns ALL

```
---

## 8. Most Common Commands

```bash

# Add 2 nodes
mgmt clusters add node --cluster gpu-cluster --count 2

# Remove two specific nodes
mgmt nodes terminate --nodes gpu-7001,gpu-7002

# Remove all compute nodes in the cluster
mgmt nodes terminate --fields "role=compute,cluster_name=gpu-cluster"

# Delete the entire cluster
mgmt clusters delete --cluster gpu-cluster

# Refresh mgmt/controller state
mgmt services all

# Verify Slurm
sinfo -p gpu-compute

```
