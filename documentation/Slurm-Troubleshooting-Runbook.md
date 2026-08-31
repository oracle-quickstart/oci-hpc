# Slurm Troubleshooting Runbook

This is an incident runbook for an OCI HPC Slurm cluster. It is written for the engineer who has the cluster in front of them.

Use the procedure that matches the symptom. Run the **check** commands first. Do not skip directly to restarts, node deletion, or controller recovery.

> **Before you start:** replace every value in `<angle-brackets>`. Record the command, the time with timezone, and the output. This creates the evidence needed to make the next runbook change additive instead of repeating the same investigation.

### Version badges used in this guide

The badges refer to the **OCI HPC stack version**, not the Slurm package version.

| Badge | Meaning |
| --- | --- |
| ![All stacks][all-stacks-badge] | The procedure is not tied to one known OCI HPC stack release. |
| ![Legacy stack 2.10.x and earlier][legacy-stack-badge] | Use only on older static-node deployments, normally stack 2.10.x and earlier. |
| ![Dynamic stack 2.11.x and later][dynamic-stack-badge] | Use only when nodes register dynamically with `slurmd -Z --conf-server`. This includes 2.11.x and later dynamic deployments. |
| ![Stack 3.x][stack-3-badge] | Use on 3.x deployments that manage topology through `/etc/slurm/topology.yaml` and the `mgmt` workflow. |
| ![Early stack 3.1][early-3-1-badge] | A compatibility procedure retained for early 3.1 deployments where the named legacy helper still exists. |
| ![Verify version][verify-version-badge] | Identify the deployment version and topology format before choosing a fix. |

Do not choose a procedure from the Slurm version alone. Two deployments can run similar Slurm packages but use different OCI HPC stack workflows.

## 1. First five minutes

Run these commands on the controller or a login node.

```bash
date -Is
sinfo -V
sinfo
squeue
sudo find /etc/slurm -maxdepth 1 -type f \
  \( -name 'topology.yaml' -o -name 'topology.conf' \) -print
```

Start every incident or deployment record with this marker:

```text
Deployment name: <deployment-or-cluster-name>
OCI HPC stack version: <stack-version-from-the-deployment-record>
Slurm version: <output-of-sinfo--V>
Topology source: </etc/slurm/topology.yaml|/etc/slurm/topology.conf|none>
Observed at: <ISO-8601-time-with-timezone>
```

If the stack version is unknown, stop before using a version-specific fix. Confirm it from the Resource Manager deployment or the deployment release record.

For a job incident, collect:

```bash
squeue -j <job-id> -o '%.18i %.9P %.8T %.40R'
scontrol show job <job-id>
```

For a node incident, collect:

```bash
sinfo -n <node-name>
scontrol show node <node-name>
```

Use this table as the index for every resolution in this runbook. The **first check** is safe. The **resolution** tells you where the exact command sequence lives.

| What you see | First check | Resolution |
| --- | --- | --- |
| ![All stacks][all-stacks-badge] User cannot submit a job after limits were enabled | `sudo sacctmgr show user <user> withassoc` | Add or correct the Slurm account association; see section 4. |
| ![All stacks][all-stacks-badge] User needs a GPU, job-count, or GPU-minute limit changed | `sudo sacctmgr show associations` | Change the approved `GrpTRES`, `GrpTRESMins`, or `MaxJobs` limit; see section 4.1. |
| ![All stacks][all-stacks-badge] Job is pending with `Resources` or “not enough resources” | `squeue -j <job-id> -o '%.18i %.9P %.8T %.40R'` | Check the exact request, out-of-Slurm GPU use, and `slurmd`; see section 5. |
| ![All stacks][all-stacks-badge] Node is `DRAIN` after resource exhaustion | `scontrol show node <node-name>` | Correct the cause, then resume with `sudo scontrol update state=resume nodename=<node-name>`; see section 6.1. |
| ![All stacks][all-stacks-badge] Node drains after an enroot/Pyxis job | `sudo stat -c '%a %U:%G %n' /mnt/localdisk/enroot` | Restore the enroot path and `0777` mode, clear any prolog health-check failure, then resume; see section 6.2. |
| ![Stack 3.x][stack-3-badge] Newly added node remains `resv` in `InitialValidation` | `scontrol show reservation InitialValidation` | Check whether active and multi-node health checks were submitted; do not remove the reservation until the validation state is understood; see section 6.4. |
| ![All stacks][all-stacks-badge] Node stays in `COMPLETING` | `squeue -w <node-name>` | Inspect job cleanup/storage first; use down-delete-restart only as advanced recovery; see section 6.3. |
| ![All stacks][all-stacks-badge] Node is `DOWN` after reboot but `slurmd` is healthy | `sudo systemctl status slurmd --no-pager` | Resume it with `sudo scontrol update NodeName=<node-name> State=RESUME`; for `Invalid user id`, use the `slurm`-user fallback in section 6.1. |
| ![All stacks][all-stacks-badge] `sinfo` hangs or the controller does not start | `sudo systemctl status slurmctld --no-pager` | Read `slurmctld.log`, correct the reported configuration issue, then restart the controller; see section 7.1. |
| ![Verify version][verify-version-badge] Primary controller failed and HA does not recover | `sinfo` and `squeue` from another terminal | Use `scontrol takeover`, then standalone `slurmctld -R` or `-c` only if needed; see section 7.2. |
| ![Stack 3.x][stack-3-badge] `sacct` or account-based job submission fails during a controller outage | `sudo systemctl status slurmdbd --no-pager` | Verify `slurmdbd` and database failover separately from `slurmctld`; see section 7.4. |
| ![All stacks][all-stacks-badge] Controller memory is unexpectedly high | `sudo sacctmgr list runaway` | Cancel confirmed runaway jobs; treat `CR_Core_Memory` to `CR_Core` as reviewed configuration work; see section 7.3. |
| ![All stacks][all-stacks-badge] `slurmd` cannot start or connect to `slurmctld` | `sudo systemctl status slurmd --no-pager` | Compare Slurm versions, controller target, and service logs; see section 8.1. |
| ![Stack 3.x][stack-3-badge] New compute node does not join after deployment | `sudo tail -n 200 /tmp/cloud-init.log` | Check cloud-init and the `/config` mount before restarting services; see section 8.4. |
| ![All stacks][all-stacks-badge] `munge.service` blocks Slurm startup | `sudo systemctl status munge --no-pager` | Capture MUNGE service and safe ownership evidence; correct it before restarting `slurmd`; see section 8.5. |
| ![Dynamic stack 2.11.x and later][dynamic-stack-badge] `resolve_ctls_from_dns_srv` or configuration-source error after reboot | `ps -ef | grep '[s]lurmd'` | Restore DNS/configless reachability or `--conf-server`, then restart `slurmd`; see section 8.2. |
| ![All stacks][all-stacks-badge] Node cannot resolve cluster names | Check the affected hostname with the cluster-approved resolver check | Restore the resolver service with `sudo systemctl restart systemd-resolved`; see section 8.3. |
| ![Verify version][verify-version-badge] Node is missing after add, resize, reboot, or rename | `scontrol show node <node-name>` | Identify static/dynamic membership and the active topology source before reconfiguring; see sections 2 and 3. |
| ![Dynamic stack 2.11.x and later][dynamic-stack-badge] A terminated or replaced dynamic node still lingers in Slurm | `scontrol show node <node-name>` | Delete the stale Slurm record and restart `slurmd` on the replacement node so it registers again; see section 3.9. |
| ![Legacy stack 2.10.x and earlier][legacy-stack-badge] New node is isolated or logs say `switches lack access` | `sudo grep -n '^SwitchName=' /etc/slurm/topology.conf` | Derive the topology child-switch suffix from `customerLocalBlock` and repair the missing switch entry; see section 3.2. |
| ![Stack 3.x][stack-3-badge] `topology.yaml` lists two nodes but NCCL uses only one | `scontrol show topology` | Run `sudo scontrol reconfigure`, verify the loaded topology, and rerun the same NCCL test; see section 3.3. |
| ![Early stack 3.1][early-3-1-badge] New node appears but `sbatch` says `Requested topology configuration is not available` | `sudo test -f /etc/slurm/generate_slurm_topology.py` | Regenerate legacy topology only when the helper and `topology.conf` exist; see section 3.4. |
| ![Stack 3.x][stack-3-badge] Partition created with `scontrol create` disappears after a resize | `sudo grep -n '^PartitionName=<partition>' /etc/slurm/slurm.conf` | Persist the partition through the supported management configuration before resize; see section 3.6. |
| ![Verify version][verify-version-badge] Resize reports an unreachable or non-existent instance | Check `mgmt nodes list`; on legacy stack 2.10.x and earlier use `/opt/oci-hpc/bin/resize.sh list` | Remove the stale inventory entry through the version-appropriate workflow before retrying; see section 3.5. |
| ![Verify version][verify-version-badge] Resize removal fails because a retired node is in a partition | `sudo grep -n '^PartitionName=' /etc/slurm/slurm.conf` | Remove the node from each static partition, or use reservations for allocation policy; see section 3.7. |
| ![Verify version][verify-version-badge] Terminated node remains in Slurm | `scontrol show reservation` | Remove it from the reservation, then use the version-appropriate inventory and node-removal workflow; see section 3.8. |
| ![All stacks][all-stacks-badge] Job stops after it starts | Check the job output/error file and `df -h <job-working-directory>` | Fix storage or application failure, then use `slurmd.log` to confirm whether a daemon restart is needed; see section 9.1. |
| ![All stacks][all-stacks-badge] Container job fails immediately | Check `/mnt/localdisk/enroot` and job error output | Correct path, mount, permission, image, or runtime error; see sections 6.2 and 9.1. |
| ![All stacks][all-stacks-badge] GPU or multi-node job is slow | `scontrol show job <job-id>` | Verify allocation/exclusivity and run approved NCCL/RDMA tests; drain a confirmed bad node; see section 9.2. |
| ![All stacks][all-stacks-badge] A procedure did not resolve the issue | Run the evidence bundle in section 10 | Attach bounded logs, exact commands, outputs, and attempted changes before adding another fix. |

## 2. Identify static or dynamic nodes before changing Slurm

This is the most important branch in this runbook.

### ![Legacy stack 2.10.x and earlier][legacy-stack-badge] Static-node cluster

A static cluster puts hostname ranges directly in partitions. Examples:

```text
PartitionName=compute Nodes=compute-hpc-node-[1-1024],compute-permanent-node-[1-1024] Default=YES MaxTime=INFINITE State=UP
PartitionName=cpu Nodes=cpu-data-node-[1-1024],cpu-datapub-node-[1-256] Default=NO MaxTime=INFINITE State=UP
```

A node belongs because its name matches a configured range.

**Check**

```bash
scontrol show partition <partition>
scontrol show node <node-name>
sudo grep -nE '^(NodeName|PartitionName)=' /etc/slurm/slurm.conf
```

**Fix**

If the node does not match a `NodeName` range or is missing from the partition, stop and review the intended configuration. Do not add a node definition based only on a missing `sinfo` row. First complete the topology and `slurmd` checks in sections 3 and 8.

After an approved configuration change:

```bash
sudo scontrol reconfigure
sinfo -n <node-name>
```

### ![Dynamic stack 2.11.x and later][dynamic-stack-badge] Dynamic-node cluster

A dynamic cluster uses feature-based partition membership. Examples:

```text
PartitionName=compute Nodes=hpc-default,iad-h100 Default=YES
PartitionName=data Nodes=data-default Default=NO
```

The node tells the controller what it is when `slurmd` starts. A healthy service command looks like this:

```text
/usr/local/sbin/slurmd --systemd -Z --conf "Gres=gpu:H100:8 Feature=hpc-default,CN__<cluster-name>" --conf-server <controller-host>
```

**Check on the compute node**

```bash
sudo systemctl status slurmd --no-pager
ps -ef | grep '[s]lurmd'
sudo systemctl cat slurmd
```

Confirm that the command has `-Z`, `--conf-server <controller-host>`, and the expected `Feature=` value.

**Fix**

Do not add the node to a static hostname range. Correct the controller target, DNS/configless configuration, or advertised feature. Then restart only the affected node:

```bash
sudo systemctl restart slurmd
sudo systemctl status slurmd --no-pager
```

**Verify from the controller**

```bash
sinfo -n <node-name>
scontrol show node <node-name>
```

## 3. Missing node, topology, and resize checks

Use this section when a node does not appear in Slurm after a resize, add, reboot, or rename.

### 3.1 ![Verify version][verify-version-badge] Check current membership and topology source

On the controller:

```bash
scontrol show node <node-name>
scontrol show partition <partition>
scontrol show nodes | grep -oP 'NodeName=\K[^ ]+'
```

Find the topology source before changing anything:

```bash
sudo find /etc/slurm -maxdepth 1 -type f \
  \( -name 'topology.yaml' -o -name 'topology.conf' \) -print
```

For a ![Stack 3.x][stack-3-badge] deployment, inspect the generated YAML and the topology loaded by `slurmctld`:

```bash
sudo ls -l /etc/slurm/topology.yaml
sudo sed -n '1,240p' /etc/slurm/topology.yaml
scontrol show topology
```

The current 3.x file is named `topology.yaml`, not `topology.yml`. Do not create or edit `topology.conf` when `topology.yaml` is the managed source.

For a ![Legacy stack 2.10.x and earlier][legacy-stack-badge] deployment, inspect the legacy file:

```bash
sudo ls -l /etc/slurm/topology.conf
sudo grep -n '<node-name>' /etc/slurm/topology.conf
```

Before an approved manual change to the legacy file, make a backup:

```bash
sudo cp -p /etc/slurm/topology.conf \
  /etc/slurm/topology.conf.backup-$(date +%Y%m%d-%H%M%S)
```

### 3.2 ![Legacy stack 2.10.x and earlier][legacy-stack-badge] Repair a missing `topology.conf` switch after resize

**What you will see:** a newly added node is isolated after a resize, or `slurmd` reports a topology warning such as:

```text
switches lack access to <node-list>
TOPOLOGY: no switch can reach all nodes through its descendants
```

This is a targeted workaround for a missing `topology.conf` switch entry. Use it only when `/etc/slurm/topology.conf` is the deployment's topology source and after confirming that the node's RDMA metadata is correct. Do not use it on a 3.x deployment with `topology.yaml`, and do not invent a switch name.

**Check the current topology and node metadata**

```bash
sudo grep -n '^SwitchName=' /etc/slurm/topology.conf
scontrol show node <new-node-name>
```

Get the new node's `customerLocalBlock` from the approved instance metadata source. The switch suffix is derived by removing the final character from `customerLocalBlock`, then taking the final 15 characters.

```bash
customer_local_block='<customerLocalBlock-value>'
without_last_char=${customer_local_block%?}
switch_suffix=${without_last_char: -15}
printf '%s\n' "$switch_suffix"
```

For example, if the derived suffix is `<switch-suffix>` and the parent topology switch is `<parent-switch>`, the child switch name is:

```text
<parent-switch>:<switch-suffix>
```

**Fix — edit only the affected entries**

1. Back up the file using the command above.
2. Open it safely:

   ```bash
   sudoedit /etc/slurm/topology.conf
   ```

3. If the child switch already exists, add `<new-node-name>` to that child's `Nodes=` list.
4. If the child switch is missing, add it to its parent's `Switches=` list and add a child entry. Use this shape, not these literal names:

   ```text
   SwitchName=<parent-switch> Switches=<existing-child-switches>,<parent-switch>:<switch-suffix>
   SwitchName=<parent-switch>:<switch-suffix> Nodes=<new-node-name>
   ```

5. Reconfigure and verify:

   ```bash
   sudo scontrol reconfigure
   sinfo -n <new-node-name>
   scontrol show node <new-node-name>
   ```

6. If the node still does not join, read its Slurm-owned log with `sudo` and keep the warning with the incident evidence:

   ```bash
   sudo grep -i -C 3 'TOPOLOGY\|switches lack access' /var/log/slurm/slurmd.log | tail -n 200
   ```

Do not apply this workaround when the metadata-derived suffix does not match the intended topology hierarchy. Escalate with the metadata, the backed-up topology file, and the log warning instead.

### 3.3 ![Stack 3.x][stack-3-badge] `topology.yaml` is correct but NCCL uses only one node

**What you will see:** two H100 nodes are present, `/etc/slurm/topology.yaml` contains both nodes, and each host has the expected network-block metadata, but a two-node NCCL run allocates or uses only one node.

**Check on the controller**

```bash
sudo sed -n '1,240p' /etc/slurm/topology.yaml
scontrol show topology
scontrol show node <node-1>
scontrol show node <node-2>
mgmt nodes list \
  --columns hostname,cluster_name,network_block_id,rack_id,rail_id \
  --format tabular
```

Confirm that both nodes appear in `scontrol show topology` and that their network-block data matches the generated topology. A correct YAML file does not prove that `slurmctld` has loaded its latest contents.

**Fix**

Reload the managed Slurm configuration:

```bash
sudo scontrol reconfigure
```

**Verify**

```bash
scontrol show topology
sinfo -n <node-1>,<node-2>
```

Rerun the same approved two-node NCCL test. It must allocate and use both nodes. If it still uses one node, collect `scontrol show job <job-id>`, the NCCL command and output, and the section 10 evidence instead of repeating `reconfigure`.

### 3.4 ![Early stack 3.1][early-3-1-badge] Regenerate legacy topology with the helper

**Applies to:** an early stack 3.1 topology-generation pattern where `/etc/slurm/generate_slurm_topology.py` exists and `/etc/slurm/topology.conf` is still the active topology source.

**What you will see:** the node appears under the intended compute partition, but a job that requests its topology fails with:

```text
sbatch: error: Batch job submission failed: Requested topology configuration is not available
```

**Check**

```bash
sudo test -f /etc/slurm/generate_slurm_topology.py
sudo grep -n '<node-name>' /etc/slurm/topology.conf
```

If the generator is absent or the deployment uses `/etc/slurm/topology.yaml`, do not substitute this helper or the manual workaround. For `topology.yaml`, use sections 3.3 and 3.5. For an evidenced legacy missing-switch repair, use section 3.2.

**Fix**

On the controller:

```bash
cd /etc/slurm
sudo python3 generate_slurm_topology.py
sudo scontrol reconfig
```

**Verify**

```bash
sudo grep -n '<node-name>' /etc/slurm/topology.conf
sinfo -n <node-name>
srun --nodes=1 --gpus=8 nvidia-smi
```

Use the final command only when an eight-GPU test allocation is appropriate for the node shape and capacity is available. It must allocate and run successfully; otherwise preserve the scheduler error and return to sections 3.1 and 3.2.

### 3.5 ![Verify version][verify-version-badge] Common guardrails for add, remove, and resize

1. Change one node at a time.
2. When adding a node, let it complete the approved hardware and GPU validation before allowing user work.
3. Coordinate with the storage owner before changing a cluster that uses Weka or shared storage.
4. After an approved Slurm configuration change, verify the one affected node:

   ```bash
   sudo scontrol reconfigure
   sinfo -n <node-name>
   ```

For ![Stack 3.x][stack-3-badge], inspect the managed inventory and reconfigure the affected node through the supported controller action:

```bash
mgmt nodes list \
  --columns hostname,status,compute_status,controller_status,cluster_name,slurm_partition \
  --format tabular
mgmt nodes reconfigure --nodes=<node-name> --action=controller
scontrol show topology
sinfo -n <node-name>
```

For ![Legacy stack 2.10.x and earlier][legacy-stack-badge] only, if the resize workflow reports an unreachable or non-existent instance, list the legacy resize inventory before retrying:

```bash
/opt/oci-hpc/bin/resize.sh list
```

Compare the reported instance with the approved inventory. Remove a confirmed stale entry through the cluster's approved inventory workflow, then retry the resize. Do not use `resize.sh` on stack 3.x. Do not run `slurm_config.sh` as a shortcut for either case; it can regenerate configuration while the source-of-truth inventory is still wrong.

### 3.6 ![Stack 3.x][stack-3-badge] Runtime-created partition disappears after resize

**Applies to:** dynamic-node stacks where a node add/remove regenerates the Slurm configuration.

**What you will see:** a partition created with `scontrol create PartitionName=...` exists initially, but disappears or causes jobs to end when nodes are added or removed.

**Check**

```bash
scontrol show partition <partition>
sudo grep -n '^PartitionName=<partition>' /etc/slurm/slurm.conf
```

If `scontrol show partition` finds it but the `grep` command does not, the partition is runtime-only. Configuration regeneration can remove it.

**Fix**

Before the resize, persist the partition through the cluster's supported `mgmt` configuration path. Do not rely on `scontrol create` as the permanent definition. Preview the generated Slurm change first, then apply it only if the output contains the intended partition:

```bash
mgmt configurations get --name <configuration-name>
sudo mgmt configurations update-slurm --dry-run
sudo mgmt configurations update-slurm
scontrol show partition <partition>
sudo grep -n '^PartitionName=<partition>' /etc/slurm/slurm.conf
```

`update-slurm` updates the managed node, node-set, and partition entries and runs `scontrol reconfigure`. Drain nodes before removing them. If a persistent custom partition is not required, use the reservation approach in section 3.7 instead.

**Public cross-reference:** [managed partition update and verification](https://github.com/oracle-quickstart/oci-hpc/blob/master/documentation/Slurm-Partition-Runbook.md#step-4-reconcile-slurm-configuration).

### 3.7 ![Verify version][verify-version-badge] Static custom partitions block resize removal

A manually maintained partition that explicitly lists nodes can block removal. `scontrol reconfigure` fails because the removed node is still named in the partition.

**Check**

```bash
sudo grep -n '^PartitionName=' /etc/slurm/slurm.conf
```

**Fix**

Remove the retiring node from every affected static partition before the resize/remove workflow. For new allocation policies, prefer a normal feature-based compute partition plus a reservation rather than a permanent custom node list:

```bash
scontrol create reservation \
  ReservationName=<reservation-name> \
  StartTime=now \
  Duration=<days>-<hh:mm:ss> \
  Nodes=<node-list> \
  Accounts=<account> \
  Users=<user>

sbatch --reservation=<reservation-name> <job-script>
```

### 3.8 ![Verify version][verify-version-badge] A terminated node remains in Slurm

A node held by a reservation cannot be cleanly removed until it is removed from that reservation.

**Check**

```bash
scontrol show reservation
```

Also confirm that Slurm has no active work on the node:

```bash
squeue -w <terminated-node-name>
```

**Fix — advanced**

Update the reservation with the intended remaining node list, then delete the already terminated node:

```bash
scontrol update ReservationName=<reservation-name> Nodes=<remaining-node-list>
sudo scontrol delete nodename=<terminated-node-name>
```

Then remove the old host from the configuration-management inventory using the approved cluster workflow. `scontrol delete` is appropriate only for a deletable dynamic node record. For a static-node deployment, remove the retired node through its version-specific configuration and resize workflow. Do not run `scontrol delete` on a node that is still running work.

### 3.9 ![Dynamic stack 2.11.x and later][dynamic-stack-badge] Dynamic node lingers in Slurm after replacement

**Applies to:** dynamic-node clusters, normally stack 2.11.x and later. Use this when the old node record remains in Slurm after the instance was terminated or replaced, and the replacement node must register dynamically.

**Check**

On the controller, confirm that the record is stale and that it has no active work:

```bash
scontrol show node <node-name>
squeue -w <node-name>
```

On the replacement compute node, confirm that it uses the dynamic registration pattern:

```bash
sudo systemctl status slurmd --no-pager
ps -ef | grep '[s]lurmd'
```

The command must include `-Z` and `--conf-server`. Do not use this procedure for a static-node cluster until its static `NodeName` and partition configuration have been corrected.

**Fix — delete the stale Slurm record, then register the replacement**

Run this on the controller only after confirming the stale record is not running a job:

```bash
sudo scontrol delete NodeName=<node-name>
```

Then run this on the replacement compute node:

```bash
sudo systemctl restart slurmd
sudo systemctl status slurmd --no-pager
```

**Verify**

Back on the controller:

```bash
sinfo -n <node-name>
scontrol show node <node-name>
```

The node should appear with the expected dynamic features and partition membership. If it does not, do not repeat the delete. Collect `sudo tail -n 200 /var/log/slurm/slurmd.log`, then follow the topology-source and controller-target checks in sections 3.1 and 8.2.

## 4. A user cannot submit a job

**What you will see:** `sbatch` returns an association, account, or limit error after job limits are enabled.

**Check**

```bash
sudo sacctmgr show user <user> withassoc
sudo sacctmgr show associations
```

**Fix**

To place a user in the default `root` account:

```bash
sudo sacctmgr add user <user> DefaultAccount=root
```

To use a dedicated account instead:

```bash
sudo sacctmgr add account <account> Description="<purpose>" Organization="<organization>"
sudo sacctmgr add user <user> DefaultAccount=<account>
sudo sacctmgr show associations
```

If the cluster requires an explicit controller refresh after accounting changes:

```bash
sudo service slurmctld restart
```

**Verify**

Submit a small test job and record its job ID:

```bash
sbatch <test-job-script>
squeue -u <user>
```

### 4.1 Check or change user limits

These commands change policy. Use them only with the account owner’s approval.

```bash
sudo sacctmgr modify user <user> set GrpTRES=cpu=-1,mem=-1,gres/gpu=<gpu-count>
sudo sacctmgr modify user <user> set GrpTRESMins=gres/gpu=<gpu-minutes>
sudo sacctmgr modify user <user> account=<account> set MaxJobs=<count>
```

To inspect GPU usage from a date:

```bash
sreport -tminper cluster utilization --tres="gres/gpu" start=<YYYY-MM-DD>
```

## 5. Job is pending although nodes look idle

**What you will see:** the job says `Resources`, “not enough resources,” or stays pending while `sinfo` shows idle nodes.

**Check the real scheduler reason first**

```bash
squeue -j <job-id> -o '%.18i %.9P %.8T %.40R'
scontrol show job <job-id>
```

Read the requested partition, account, QOS, CPUs, memory, GRES/GPU count, node features, and constraints. Then inspect each candidate node:

```bash
scontrol show node <node-name>
```

**Check for work outside Slurm**

An idle node can still have GPUs used by processes that Slurm did not start:

On the candidate compute node:

```bash
nvidia-smi
ps -ef
```

Do not kill a process until its owner and purpose are confirmed.

**Check whether the node is really connected**

On the compute node:

```bash
sudo systemctl status slurmd --no-pager
sudo tail -n 200 /var/log/slurm/slurmd.log
```

If `slurmd` is not active or the log shows configuration-source errors, follow section 8.

**Verify**

After correcting the actual cause, rerun:

```bash
squeue -j <job-id> -o '%.18i %.9P %.8T %.40R'
```

The reason must change or the job must start. If neither happens, collect section 10 evidence before trying a different fix.

### 5.1 ![Verify version][verify-version-badge] One node cannot satisfy `--gpus-per-task`

**What you will see:** a reservation or ordinary job runs on other nodes, but a request such as `--gpus-per-task 1` returns `Requested node configuration is not available` for one node.

**Check the affected node against a working peer**

```bash
scontrol show node <affected-node-name>
scontrol show node <working-node-name>
sudo systemctl cat slurmd
ssh <working-node-name> 'sudo systemctl cat slurmd'
```

Compare `Gres=`/GPU count, features, and the `slurmd` service arguments. A matching `Gres=gpu:<count>` does not prove that dynamic registration is correct.

**Fix**

For a 2.11.x+ dynamic node with no running job, use the stale-record recovery in section 3.9. If the service definition differs, repair it through the approved configuration path before restarting `slurmd`; do not delete spool state as a first response.

## 6. Node state procedures

### 6.1 Node is `DRAIN`

**Check the reason**

```bash
scontrol show node <node-name>
sudo tail -n 200 /var/log/slurm/slurmd.log
```

For a simple resource-exhaustion drain, after confirming the problem is gone:

```bash
sudo scontrol update state=resume nodename=<node-name>
sinfo -n <node-name>
```

For a rebooted node that shows `DOWN` but `slurmd` is healthy:

```bash
sudo scontrol update NodeName=<node-name> State=RESUME
sinfo -n <node-name>
```

If that command returns `slurm_update error: Invalid user id`, retry it as the Slurm service user:

```bash
sudo -u slurm scontrol update NodeName=<node-name> State=RESUME
sinfo -n <node-name>
```

### 6.2 Node drains after a job when enroot or Pyxis is enabled

**What you will see:** a container job fails immediately, or a non-container job completes but the node becomes drained.

**Check**

```bash
sudo ls -ld /mnt/localdisk/enroot
sudo stat -c '%a %U:%G %n' /mnt/localdisk/enroot
sudo tail -n 200 /var/log/slurm/slurmd.log
```

The expected mode for `/mnt/localdisk/enroot` is `0777`.

**Fix**

Restore the approved mount/path and permissions. If a Slurm prolog health check is enabled, fix the health-check failure too. Only then resume the node:

```bash
sudo scontrol update NodeName=<node-name> State=RESUME
sinfo -n <node-name>
```

If the node drains again after resume, follow section 6.4 to collect health-check evidence before changing Slurm configuration. Treat an OCA, RDMA, GPU, or prolog failure as the cause to repair. Do not disable health checks or edit their scripts as an incident workaround.

### 6.3 Node is `COMPLETING` and will not become idle

**Check**

```bash
squeue -w <node-name>
scontrol show node <node-name>
scontrol show job <job-id>
df -h
sudo tail -n 200 /var/log/slurm/slurmd.log
```

Check for unfinished job cleanup, a full filesystem, or a service error.

![Dynamic stack 2.11.x and later][dynamic-stack-badge] **Advanced / risky recovery**

Only when normal cleanup has failed, section 10 evidence is saved, and the node uses the dynamic registration pattern from section 2:

```bash
sudo scontrol update nodename=<node-name> state=down reason=completing
sudo scontrol delete nodename=<node-name>
clush -w <node-name> sudo systemctl start slurmd
sinfo -n <node-name>
```

This deletes the dynamic Slurm record and lets `slurmd` register it again. It can interrupt work or lose job state. Do not apply it to multiple nodes at once. For a static-node deployment, do not delete the node record; correct the configured node and partition definitions instead.

### 6.4 ![Stack 3.x][stack-3-badge] New node stays in `InitialValidation` / `resv`

**Applies to:** stack 3.x clusters that reserve new nodes until passive, active, and multi-node validation completes.

**What you will see:** a newly added node is in the `InitialValidation` reservation and remains `resv`; passive checks pass, but active or multi-node health-check jobs are absent from `squeue`.

**Check**

```bash
scontrol show reservation InitialValidation
sinfo -n <node-name>
squeue -w <node-name>
mgmt nodes healthchecks --nodes=<node-name>
mgmt nodes healthchecks --nodes=<node-name> --type active
mgmt nodes healthchecks --nodes=<node-name> --type multi-node
sudo du -h /var/log/syslog
df -h /var/log
```

Run one targeted active health check to distinguish a scheduler submission problem from a node failure:

```bash
sbatch -N 1 -w <node-name> /opt/oci-hpc/healthchecks/active_HC.sbatch
```

**Fix**

If the active health check fails, repair that reported GPU, RDMA, or host issue and rerun it. A very large `/var/log/syslog` can also make health checks hang or take unusually long; correct the underlying log-growth issue through the approved operating-system logging process. If passive checks pass but no active or multi-node check is ever submitted, collect the command output, `squeue`, and the controller logs from section 10. Do not patch `/config/mgmt/lib/database.py` directly on a customer cluster; treat that as a stack defect to fix through the supported release or a reviewed patch.

Do not remove `InitialValidation` merely to make capacity available. In the documented 3.x workflow, a node that completes active checks but cannot complete multi-node checks should leave the reservation automatically after the configured timeout. If it does not, escalate with the evidence.

**Public cross-reference:** [active health checks and `InitialValidation`](https://github.com/oracle-quickstart/oci-hpc/blob/master/documentation/Troubleshooting.md#slurm-reservation) and the [`mgmt nodes healthchecks` options](https://github.com/oracle-quickstart/oci-hpc/blob/master/documentation/mgmt-cli.md#nodes-healthchecks).

## 7. sinfo hangs, slurmctld fails, or controller memory is high

### 7.1 sinfo hangs

**Check the controller**

```bash
sudo systemctl status slurmctld --no-pager
sudo tail -n 200 /var/log/slurm/slurmctld.log
sudo journalctl -u slurmctld --since '30 minutes ago' --no-pager
```

A missing or malformed `$SLURMCTLD_OPTIONS` setting in the service configuration can prevent `slurmctld` from starting. Fix the reported configuration problem before restarting the service.

```bash
sudo systemctl restart slurmctld
sudo systemctl status slurmctld --no-pager
sinfo
```

### 7.2 Controller recovery and HA failover

**Advanced / risky.** These are controller-state recovery commands. They can affect all jobs.

1. If the primary controller failed and a backup is available, log into the backup controller and run:

   ```bash
   scontrol takeover
   ```

2. In another terminal, check whether service returned:

   ```bash
   sinfo
   squeue
   ```

3. If failover did not restore service, run this **outside systemd** on the controller:

   ```bash
   sudo slurmctld -R
   ```

   For detailed foreground output:

   ```bash
   sudo slurmctld -R -Dvvv
   ```

4. If recovery still fails, restore the controller state from its last checkpoint:

   ```bash
   sudo slurmctld -c
   ```

   Wait for it to load, check `sinfo` and `squeue` from another terminal, then stop the standalone process with `Ctrl-C`.

5. Return to systemd service management:

   ```bash
   sudo systemctl restart slurmctld
   ```

6. Restart `slurmd` across the affected compute nodes:

   ```bash
   pdsh -R ssh -w <all-gpu-nodes> sudo systemctl restart slurmd
   ```

A checkpoint recovery can lose some or all job state. Capture section 10 evidence and tell users that jobs may need to be restarted.

### 7.3 Controller memory is unusually high

**Check for runaway jobs**

```bash
sudo sacctmgr list runaway
```

If a job is confirmed runaway:

```bash
scancel <job-id>
```

For a reviewed configuration change intended to reduce controller memory, change:

```text
SelectTypeParameters=CR_Core_Memory
```

to:

```text
SelectTypeParameters=CR_Core
```

Then apply it:

```bash
sudo scontrol reconfig
```

This changes scheduling behavior. Treat it as a configuration change, not an incident-time quick fix.

### 7.4 ![Stack 3.x][stack-3-badge] HA controller recovered, but accounting is unavailable

**Applies to:** stack 3.0+ HA deployments with a backup controller and managed MySQL. It does not describe the older 2.x design where accounting may have been tied to the primary controller.

**What you will see:** `sinfo` and `squeue` return after controller failover, but `sacct`, `sacctmgr`, or account-restricted job submission fails.

**Check both control-plane services on the backup**

```bash
sudo systemctl status slurmctld --no-pager
sudo systemctl status slurmdbd --no-pager
sudo tail -n 200 /var/log/slurm/slurmctld.log
sudo tail -n 200 /var/log/slurm/slurmdbd.log
sacct -S now-1hour
```

The backup controller log should show that it is acting as primary. If `slurmdbd` has also failed over, its log should show the takeover/startup event. If `sacct` fails, preserve its exact error; do not assume that a working `slurmctld` proves accounting is healthy.

**Fix**

Restore the failed `slurmctld` or `slurmdbd` service using the approved HA recovery procedure for the deployed stack version. Do not stop a healthy controller, `slurmdbd`, or database merely to test failover during an incident.

**Public cross-reference:** [backup-controller service layout](https://github.com/oracle-quickstart/oci-hpc/blob/master/documentation/Setup.md#create-a-slurm-backup-controller).

## 8. slurmd fails to start or cannot fetch configuration

### 8.1 Basic slurmd check

On the compute node:

```bash
sudo systemctl status slurmd --no-pager
sudo tail -n 200 /var/log/slurm/slurmd.log
sudo journalctl -u slurmd --since '30 minutes ago' --no-pager
```

On the controller:

```bash
sudo systemctl status slurmctld --no-pager
sudo tail -n 200 /var/log/slurm/slurmctld.log
```

Confirm controller and compute node use compatible Slurm versions:

```bash
# On the controller
slurmctld -V

# On the compute node
slurmd -V
```

### 8.2 ![Dynamic stack 2.11.x and later][dynamic-stack-badge] DNS SRV / configless error after reboot

**What you will see:**

```text
resolve_ctls_from_dns_srv: res_nsearch error: Unknown host
fetch_config: DNS SRV lookup failed
Could not establish a configuration source
```

**Check**

```bash
sudo systemctl status slurmd --no-pager
ps -ef | grep '[s]lurmd'
```

For a dynamic node, confirm the service contains the expected `--conf-server <controller-host>` option. Check name resolution and the cluster’s approved DNS/configless configuration.

**Fix**

After restoring controller reachability or configuration source:

```bash
sudo systemctl restart slurmd
sudo systemctl status slurmd --no-pager
```

**Verify from controller**

```bash
sinfo -n <node-name>
scontrol show node <node-name>
```

### 8.3 Node cannot resolve names

Check resolution before restarting any service:

```bash
getent hosts <controller-host>
getent hosts <node-name>
resolvectl query <controller-host>
```

If the controller or node name does not resolve, check the resolver service:

```bash
sudo systemctl restart systemd-resolved
```

Repeat the three checks above. Retry `slurmd` only after the controller and affected node resolve correctly.

### 8.4 ![Stack 3.x][stack-3-badge] New compute node does not join after deployment

**Applies to:** reported stack 3.0 deployment failures.

**Check the node bootstrap before restarting Slurm**

```bash
sudo tail -n 200 /tmp/cloud-init.log
sudo tail -n 200 /var/log/cloud-init.log
sudo ls -ld /config /config/bin
sudo ls -l /config/bin/compute.sh
sudo ls -lt /config/logs | head
```

`/config` must be mounted during cloud-init. A missing `/config/bin/compute.sh` or cloud-init error indicates a bootstrap/config-mount problem, not a Slurm scheduler problem.

**Fix and verify**

Correct the reported cloud-init or configuration-mount failure through the approved deployment workflow. Then confirm bootstrap completed and only then check Slurm:

```bash
sudo systemctl status slurmd --no-pager
sudo tail -n 200 /var/log/slurm/slurmd.log
sinfo -n <node-name>
```

### 8.5 MUNGE prevents Slurm services from starting

**What you will see:** `slurmd` or `slurmctld` fails to authenticate or start, and `munge.service` is failed.

**Check without exposing the key**

```bash
sudo systemctl status munge --no-pager
sudo journalctl -xeu munge.service --no-pager
sudo ls -ld /run/munge /var/log/munge
sudo stat -c '%a %U:%G %n' /etc/munge/munge.key
```

Capture errors such as permission failures opening the runtime or log directory. Do not print, copy, or change the contents of `/etc/munge/munge.key`.

**Fix and verify**

Restore the approved ownership and permissions for the reported MUNGE runtime, log, or key path through the cluster configuration process. Then:

```bash
sudo systemctl restart munge
sudo systemctl status munge --no-pager
sudo systemctl restart slurmd
sudo systemctl status slurmd --no-pager
```

If MUNGE still fails, attach the bounded MUNGE journal output and the `stat` output to the incident evidence; do not guess at permission values.

## 9. Job stops, job output, and slow GPU jobs

### 9.1 Job stops after running for a while

**Check job output first.** Slurm writes output to the path set by `#SBATCH --output` and errors to `#SBATCH --error`. If neither is set, look in the submit directory for `slurm-<job-id>.out`.

Then check the job working directory and node storage:

```bash
df -h <job-working-directory>
df -ih <job-working-directory>
sudo tail -n 200 /var/log/slurm/slurmd.log
```

Fix storage exhaustion or the application error first. Restart `slurmd` only if its log shows a daemon failure.

### 9.2 GPU or multi-node job is slow

**Check allocation**

```bash
scontrol show job <job-id>
```

Confirm whether the job is exclusive. Run the approved NCCL and RDMA tests on the allocated nodes. Compare with a known-good node set. If one node is bad, drain that node and attach the test results to the evidence bundle.

## 10. Logs and evidence for unresolved incidents

Slurm log files are owned by the `slurm` user. Use `sudo` when reading them.

Copy the deployment marker from section 1 into the incident before collecting logs. This prevents a later engineer from applying a `topology.conf`, `topology.yaml`, or `resize.sh` fix to the wrong stack generation.

| Need | Command |
| --- | --- |
| Controller errors | `sudo tail -n 200 /var/log/slurm/slurmctld.log` |
| Accounting-daemon errors | `sudo tail -n 200 /var/log/slurm/slurmdbd.log` |
| Compute-node errors | `sudo tail -n 200 /var/log/slurm/slurmd.log` |
| Controller service events | `sudo journalctl -u slurmctld --since '30 minutes ago' --no-pager` |
| Compute-node service events | `sudo journalctl -u slurmd --since '30 minutes ago' --no-pager` |
| One job/node in the node log | Use the command immediately below. |

Use a bounded time range, not a full log dump:

```bash
sudo journalctl -u slurmd \
  --since '<YYYY-MM-DD HH:MM:SS>' \
  --until '<YYYY-MM-DD HH:MM:SS>' \
  --no-pager
```

For one known job or node:

```bash
sudo grep -i -C 3 '<job-id-or-node-name>' /var/log/slurm/slurmd.log | tail -n 200
```

When the issue is not fixed, collect the relevant block below. Do not run job commands for a node-only incident or node commands for a controller-only incident.

**Job incident**

```bash
date -Is
sinfo -V
squeue -j <job-id>
scontrol show job <job-id>
```

**Node incident**

```bash
date -Is
sinfo -n <node-name>
scontrol show node <node-name>
sudo systemctl status slurmd --no-pager
sudo tail -n 200 /var/log/slurm/slurmd.log
```

**Controller or accounting incident**

```bash
date -Is
sinfo
squeue
sudo systemctl status slurmctld --no-pager
sudo systemctl status slurmdbd --no-pager
sudo tail -n 200 /var/log/slurm/slurmctld.log
sudo tail -n 200 /var/log/slurm/slurmdbd.log
```

Add the exact error, the affected user/account/partition, relevant job output, each action attempted, and the result of that action. Redact passwords, tokens, JWTs, credentials, private IP addresses, and private customer identifiers before sharing.

## 11. Add a new solved case

When you solve a new case, add it under the closest existing symptom using this structure:

1. **Deployment marker** — stack version, Slurm version, topology source, and observation time from section 1.
2. **What you will see** — exact error, state, or behavior.
3. **Applies to** — use one guide badge and state the known version boundary.
4. **Check** — exact commands and expected result.
5. **Fix** — smallest safe corrective action.
6. **Verify** — exact command and successful result.
7. **If it still fails** — specific evidence needed next.

Do not create another generic troubleshooting list. Add the new evidence-backed procedure beside the symptom it improves.

[all-stacks-badge]: https://img.shields.io/badge/Scope-All%20Stacks-5B6470?style=flat-square
[legacy-stack-badge]: https://img.shields.io/badge/Stack-%E2%89%A42.10.x-B54708?style=flat-square
[dynamic-stack-badge]: https://img.shields.io/badge/Stack-2.11.x%2B-175CD3?style=flat-square
[stack-3-badge]: https://img.shields.io/badge/Stack-3.x-067647?style=flat-square
[early-3-1-badge]: https://img.shields.io/badge/Stack-Early%203.1-6941C6?style=flat-square
[verify-version-badge]: https://img.shields.io/badge/Version-Verify-D92D20?style=flat-square
