# Runbook: Run Passive, Active, and Multi-Node Healthcheck and NCCL Tests 


## 🔹 Overview
This runbook describes the validated user workflow to run NCCL tests through the `mgmt` CLI on an existing OCI GPU cluster.

In this implementation, `mgmt` does not expose a standalone `nccl` subcommand. NCCL is executed through healthcheck workflows:
- Single-node NCCL via `active` healthcheck
- Multi-node NCCL via `multi-node` healthcheck

Observed and validated behavior:
- Effective healthcheck log root on the deployed cluster was `/var/log/healthchecks`
- `mgmt services active-hc` may skip eligible reserved nodes when active HC state is `NULL`
- Reliable workaround is to force active HC with `mgmt nodes healthchecks --type active ...`
- `mgmt services multi-node-hc` is schedule-driven and will not rerun nodes that already have a recent multi-node HC result
- `mgmt nodes healthchecks --type multi-node ...` is the user-triggered path for immediate reruns
- On large clusters, build the node list with `sinfo` and pass it as a comma-separated `--nodes` value

## 🔹 Procedure

### 1️⃣ Discover target node names
For a large cluster, use `sinfo` in node-expanded mode and deduplicate by hostname.

Set the reservation if needed:
```
export RESERVATION=InitialValidation
```
All compute nodes:
```bash
sinfo -N -h -p compute -o "%N" | sort -u
```

Only idle compute nodes:
```bash
sinfo -N -h -p compute -t idle -o "%N" | sort -u
```

Build a comma-separated list of all compute nodes:
```bash
export NODES="$(
  sinfo \
    -N -h \
    -p compute \
    -o "%N" | \
  sort -u | \
  paste -sd, -
)"
```

Expected:
- One hostname per line when using `-N -h -o "%N" | sort -u`
- No duplicates even if nodes appear in multiple partitions
- `NODES` is comma-separated and suitable for `mgmt --nodes`

### 2️⃣ Confirm cluster and reservation state
```bash
mgmt nodes list \
  --format json \
  --columns \
hostname,shape,slurm_state,slurm_reservation,\
passive_healthcheck_recommendation,\
active_healthcheck_recommendation,\
multi_node_healthcheck_recommendation \
  --fields role=compute

scontrol show reservation "$RESERVATION"

sinfo
```



Expected:
- Target GPU nodes are present
- Target nodes show the expected GPU shape
- Target nodes appear in `compute` and `default-healthcheck`
- Reservation exists if the nodes are still under initial validation
###  3️⃣ Run passive HC on target nodes
Passive HC runs the host setup validation path through `check_gpu_setup.py`. It is the passive healthcheck used by `mgmt` and it does not run as a Slurm batch job. It runs directly on the target nodes.

Run passive HC on all compute nodes:
```bash
export NODES="$(sinfo -N -h -p compute -o "%N" | sort -u | paste -sd, -)"
mgmt nodes healthchecks --type passive --nodes "$NODES"
```
###  4️⃣ Check passive HC logs
The Passive HC log file on each node is stored at `/var/log/healthchecks/latest_healthcheck.log`.

Read the full passive log from all nodes:
```bash
for node in $(
  echo "$NODES" | tr ',' ' '
); do
  echo "===== $node ====="

  ssh "$node" \
    'sudo cat \
      /var/log/healthchecks/latest_healthcheck.log \
      2>/dev/null || echo "log not found"'
done
```

Check one node:
```bash
ssh <node> 'sudo tail -f /var/log/healthchecks/latest_healthcheck.log'
```

Refresh `mgmt` metadata after passive HC:
```bash
mgmt --debug services update-metadata

mgmt nodes list \
  --format json \
  --columns hostname,\
passive_healthcheck_recommendation,\
passive_healthcheck_last_time \
  --fields role=compute
```
###  5️⃣ Run single-node active HC on target nodes
Active HC is the single-node GPU validation path. On NVIDIA GPU nodes it includes a NCCL test.
Example for all nodes:

```bash
mgmt nodes healthchecks --type active --nodes "$NODES" 

```

Expected:
- One or more `active_HealthCheck` jobs are submitted
- On a large cluster, jobs may be staggered depending on Slurm state and reservation eligibility

Check Slurm:
```bash
squeue \
  -u "$USER" \
  -n active_HealthCheck \
  -o "%.18i %.30j %.8T %.10M %.20R"
```



Expected:
- Active HC jobs move to `RUNNING` and later complete

###  6️⃣ Check single-node active HC logs
On the validated cluster, the effective path is `/var/log/healthchecks` on each node.

Check a sample of target nodes:
```bash
for node in $(echo "$NODES" | tr ',' ' ' | head -20); do
  echo "===== $node ====="
  ssh "$node" \
  'sudo tail -50 \
/var/log/healthchecks/latest_active_healthcheck.log \
2>/dev/null || echo "log not found"'
done
```



Check one specific node:
```bash
ssh <node> \
  'sudo tail -f \
    /var/log/healthchecks/latest_active_healthcheck.log'
```

Expected:
- Log contains lines similar to:
```text
NCCL Test Succeeded: Avg bus bandwidth is <value>
GPU Fryer Test Succeeded
GPU Silent Data Corruption Test Succeeded
NVME Test Succeeded
Finished GPU host setup check
```

###  7️⃣ Refresh `mgmt` metadata after active HC finishes
Do not skip this step.

```bash
mgmt --debug services update-metadata

mgmt nodes list \
  --format json \
  --columns \
hostname,slurm_state,slurm_reservation,\
active_healthcheck_recommendation,\
active_healthcheck_last_time \
  --fields role=compute
```




Expected:
- Target nodes show `active_healthcheck_recommendation = Healthy`
- `active_healthcheck_last_time` is populated

###  8️⃣ Run multi-node active HC on target nodes
There are two relevant ways to invoke multi-node HC:

Scheduled runner:
```bash
mgmt --debug services multi-node-hc
```

User triggered immediate run:
```bash
mgmt nodes healthchecks --type multi-node --nodes "$NODES" 
```

Important behavior:
- `mgmt services multi-node-hc` is schedule-driven
- it will not rerun nodes that already have a recent multi-node HC result
- `mgmt nodes healthchecks --type multi-node ...` is the correct immediate rerun path
- it does not create one giant all-node NCCL job
- it iterates anchor nodes and submits multi-node healthcheck jobs per anchor node




Important:
- `mgmt services multi-node-hc` is schedule-driven and will not rerun nodes that already have a recent multi-node HC result
- `mgmt nodes healthchecks --type multi-node --nodes "$NODES" ...` does not create one giant all-node NCCL job
- The CLI iterates the anchor nodes and submits multi-node healthcheck jobs per anchor node

Check the queue:
```bash
squeue \
  -u "$USER" \
  -o "%.18i %.30j %.8T %.10M %.20R" \
| grep multi_node_active_HealthCheck
```



Expected:
- One or more multi-node jobs are submitted
- Jobs move to `RUNNING` when the required nodes are available simultaneously

### 9️⃣ Check multi-node active HC logs
First inspect the jobs:
```bash
squeue \
  -u "$USER" \
  -o "%.18i %.30j %.8T %.10M %.20R" \
| grep multi_node_active_HealthCheck
```

After jobs finish, inspect accounting:
```bash
sacct \
  --user "$USER" \
  --name multi_node_active_HealthCheck \
  --starttime today \
  --format JobID,JobName,State,ExitCode,NodeList
```




Inspect one specific job:
```bash
scontrol show job <jobid>
```

This shows:
- `NodeList`
- `BatchHost`
- `StdOut`
- `StdErr`

For actual NCCL and IB results, the log is:
```bash
/var/log/healthchecks/latest_multi_node_active_healthcheck.log
```

Check all target nodes:
```bash
for node in $(
  echo "$NODES" | tr ',' ' '
); do
  echo "===== $node ====="

  ssh "$node" \
    'sudo tail -50 \
      /var/log/healthchecks/latest_multi_node_active_healthcheck.log \
      2>/dev/null || echo "log not found"'
done
```


Check one node:
```bash
ssh <node> \
  'sudo tail -f \
    /var/log/healthchecks/latest_multi_node_active_healthcheck.log'
```

Check batch stdout directories if needed:
```bash
for node in $(
  echo "$NODES" | tr ',' ' '
); do
  echo "===== $node ====="

  ssh "$node" \
    'sudo ls -ltr \
      /var/log/healthchecks/multi_node_active_HealthCheck/ \
      2>/dev/null || echo "stdout dir not found"'
done
```

Expected:
- Multi-node logs contain lines similar to:
```text
NCCL Test Succeeded: Avg bus bandwidth is <value>
ib write bw Test Succeeded
ib write latency Test Succeeded
Finished multi-node active healthcheck
```

Validated example:
- `NCCL Test Succeeded: Avg bus bandwidth is 185.591`

### 1️⃣0️⃣ Refresh metadata after multi-node HC
```bash
mgmt --debug services update-metadata

mgmt nodes list \
  --format json \
  --columns hostname,\
multi_node_healthcheck_recommendation,\
multi_node_healthcheck_last_time,\
active_healthcheck_recommendation \
  --fields role=compute
```

Expected:
- `multi_node_healthcheck_recommendation` is populated for participating nodes
- Multi-node result is visible in `mgmt`
