# Enable Monitoring After Deployment

This guide describes how to enable monitoring on an existing OCI HPC/Slurm
cluster that was deployed with monitoring disabled.

It covers two workflows:

- Enable monitoring on the existing controller when there is no dedicated
  monitoring node.
- Add a new dedicated monitoring VM and configure monitoring on that node.

Replace the placeholder values in the examples before running commands:

| Placeholder               | Meaning                                                                                                                              |
| ---                       | ---                                                                                                                                  |
| `<cluster_name>`          | Cluster name                                                                                                                         |
| `<cluster_admin_user>`    | Existing `cluster_admin_user` value in the generated inventory, usually `ubuntu` or `opc`, can be used to log into the monitoring VM |
| `<controller_hostname>`   | Controller hostname, for example `<cluster_name>-controller`                                                                         |
| `<monitoring_hostname>`   | Monitoring VM hostname, for example `<cluster_name>-monitoring`                                                                      |
| `<monitoring_private_ip>` | Private IP address of the monitoring VM                                                                                              |

## Recommended Monitoring Features

For Slurm clusters, we recommend enabling Slurm job monitoring, OCI metrics
ingestion, and alerting. Together they provide job history, OCI telemetry, and
Grafana alert notifications.

## Start Here

Choose what to enable:

- **Core monitoring only:** Grafana, Prometheus, and node exporters. Skip the
  Resource Manager update and the common post-apply configuration steps.
- **Core monitoring plus additional features:** enable one or more features in
  Resource Manager, run **Plan** and **Apply**, then complete the common
  post-apply configuration steps before starting either scenario.

For an existing cluster, Apply creates OCI resources only. It does not refresh
the inventories in `/config/playbooks`, update group variables, or run Ansible.

| Monitoring feature | Resource Manager variables | Requirements |
| --- | --- | --- |
| Slurm job monitoring | `slurm_job_monitoring=true`, `slurm_monitoring_mysql_backend=local\|managed` | Requires `slurm=true`. The `managed` backend also requires the MySQL Database Options values, including `mysql_shape`, `mysql_admin_username`, and `mysql_admin_password`. |
| OCI metrics / Telegraf | `ingest_oci_metrics=true` | Apply the stack update to create the OCI Streaming stream and Service Connector. Manually refresh `metrics_stream_ocid` in the controller inventories before running the monitoring configuration. |
| OCI alerting | `alerting=true` | Apply the stack update to create the OCI Notifications topic. Manually refresh `ons_topic_ocid` in the controller inventories before running the monitoring configuration. |
| Grafana LDAP | `grafana_ldap_auth_enabled=true` | Requires `ldap=true`. |
| Grafana TLS | `use_lets_encrypt_prod_ep=true\|false` | Keep the stack value appropriate for the deployment; this option is not available for private deployments. |

Do not set `slurm_job_monitoring=true`, `ingest_oci_metrics=true`, or
`alerting=true` directly in the inventory. Those inventory values do not create
the required supporting resources or configuration.

## Choose a Scenario

- Continue with [Scenario 1](#scenario-1-enable-monitoring-on-the-controller)
  to run monitoring on the existing controller.
- Continue with [Scenario 2](#scenario-2-add-a-dedicated-monitoring-node) to
  create and configure a dedicated monitoring VM.

## Common Post-Apply Configuration

Complete this section only when you enabled additional features in Resource
Manager after deployment. Skip it for core monitoring only.

### 1. Download and protect the Terraform state

In the OCI Console, open the stack and download its Terraform state to a
protected workstation location. The state contains passwords. Do not upload it,
commit it, or attach it to a ticket.

Set `STATE_FILE` to that downloaded file. The following read-only `jq` commands
show the non-secret values required for the inventory. Run them only from a
trusted terminal:

```bash
export STATE_FILE=<path-to-downloaded-terraform-state.json>

jq -r '.resources[]
  | select(.mode == "data" and .type == "oci_mysql_mysql_db_system" and .name == "slurm_mysql")
  | .instances[0].attributes.endpoints[0].ip_address' "$STATE_FILE"

jq -r '.resources[]
  | select(.type == "oci_streaming_stream" and .name == "telegraf_stream")
  | .instances[0].attributes.id' "$STATE_FILE"

jq -r '.resources[]
  | select(.type == "oci_ons_notification_topic" and .name == "grafana_alerts")
  | .instances[0].attributes.id' "$STATE_FILE"
```

Use only the values for the features you enabled:

| State value | Inventory setting |
| --- | --- |
| Managed MySQL endpoint private IP | `mysql_service_host` and `slurm_monitoring_db_host` |
| Streaming stream OCID | `metrics_stream_ocid` |
| Notifications topic OCID | `ons_topic_ocid` |

For **managed MySQL job monitoring**, also retrieve these generated passwords:

```text
random_password.slurm_monitoring_db_pwd.result
random_password.slurm_monitoring_grafana_db_pwd.result
```

For a raw Terraform state download, retrieve each value with the corresponding
resource address below. These commands print secrets, so run them only in a
private terminal and transfer the values directly into the editor in step 4:

```bash
jq -r '.resources[]
  | select(.type == "random_password" and .name == "slurm_monitoring_db_pwd")
  | .instances[0].attributes.result' "$STATE_FILE"

jq -r '.resources[]
  | select(.type == "random_password" and .name == "slurm_monitoring_grafana_db_pwd")
  | .instances[0].attributes.result' "$STATE_FILE"
```

Use the `mysql_admin_password` entered in the Resource Manager form. Do not use
Terraform's `random_password.mysql_admin_pwd` fallback when a form password was
provided.

### 2. Back up the generated configuration on the controller

SSH to the controller and run:

```bash
CLUSTER=$(awk -F= '/^cluster_name=/{print $2; exit}' /config/playbooks/inventory)
BASE_INVENTORY=/config/playbooks/inventory
ACTIVE_INVENTORY="/config/playbooks/inventory_${CLUSTER}"
MONITORING_VARS=/config/playbooks/group_vars/all/monitoring.yml
STAMP=$(date +%Y%m%d-%H%M%S)

sudo cp "$BASE_INVENTORY" "${BASE_INVENTORY}.pre-post-apply-${STAMP}.bak"
sudo cp "$ACTIVE_INVENTORY" "${ACTIVE_INVENTORY}.pre-post-apply-${STAMP}.bak"
sudo cp "$MONITORING_VARS" "${MONITORING_VARS}.pre-post-apply-${STAMP}.bak"
```

Keep these backups on the cluster. They contain credentials after the update.

### 3. Update both inventories

Open the base inventory:

```bash
sudoedit "$BASE_INVENTORY"
```

Under `[all:vars]`, replace existing values; do not add duplicate keys. Add
only the settings for features you enabled. Set `monitoring_hostname` in the
selected scenario: controller for Scenario 1, monitoring VM for Scenario 2.

```ini
cluster_monitoring=true

slurm_job_monitoring=true
slurm_monitoring_mysql_backend=managed
mysql_admin_username=<mysql-administrator-name>
mysql_service_host=<managed-mysql-private-ip>
slurm_monitoring_db_host=<managed-mysql-private-ip>
slurm_monitoring_db_port=3306
slurm_monitoring_db_name=slurm_jobs
slurm_monitoring_db_user=slurm_exporter
slurm_monitoring_grafana_db_user=slurm_grafana

metrics_stream_ocid=<stream-ocid>
ons_topic_ocid=<notification-topic-ocid>
```

Repeat the same edits in the active, cluster-specific inventory:

```bash
sudoedit "$ACTIVE_INVENTORY"
```

Do not copy the base inventory over the active inventory: it can discard
runtime inventory information. Update the listed keys in both files instead.

### 4. Update passwords (managed MySQL only)

Ansible loads `/config/playbooks/group_vars/all/monitoring.yml` with higher
precedence than inventory values. Updating passwords only in either inventory
will not work. Open the file:

```bash
sudoedit "$MONITORING_VARS"
```

Replace the values for these existing YAML keys with the secure values recorded
in step 1. Preserve the existing YAML syntax and `!unsafe` marker:

```yaml
mysql_admin_password: !unsafe "<mysql-administrator-password>"
slurm_monitoring_db_password: !unsafe "<generated-exporter-password>"
slurm_monitoring_grafana_db_password: !unsafe "<generated-grafana-password>"
```

Do not paste the passwords into shell commands, ticket comments, or command
output. Enter them only in the editor.

### 5. Check the refresh

Confirm that all required non-secret inventory values are present:

```bash
grep -E '^(cluster_monitoring|monitoring_hostname|slurm_job_monitoring|slurm_monitoring_mysql_backend|mysql_admin_username|mysql_service_host|slurm_monitoring_db_host|metrics_stream_ocid|ons_topic_ocid)=' \
  "$BASE_INVENTORY" "$ACTIVE_INVENTORY"
```

Confirm that the three password values are set, without printing them:

```bash
sudo awk -F: '/^(mysql_admin_password|slurm_monitoring_db_password|slurm_monitoring_grafana_db_password):/ {
  value=$2; sub(/^[[:space:]]*/, "", value)
  print $1 ": " (length(value) ? "<set>" : "<empty>")
}' "$MONITORING_VARS"
```

For managed MySQL, continue only when each password reports `<set>`. Scenario 1
sets `monitoring_hostname` to the controller. Scenario 2 sets it after creating
the monitoring VM.

### Initialize the Slurm Monitoring Database

Run this section only for managed-MySQL Slurm job monitoring. Apply creates the
DB System, not the `slurm_jobs` database, tables, or users. Run this temporary
playbook on the primary controller before starting monitoring.

```bash
sudo tee /config/playbooks/slurm_monitoring_database.yml >/dev/null <<'EOF'
---
- name: Initialize the Slurm monitoring database
  hosts: localhost
  connection: local
  gather_facts: true
  tasks:
    - name: Create the Slurm monitoring database, schema, and users
      ansible.builtin.include_role:
        name: slurm
        tasks_from: monitoring_db.yml
EOF

/config/bin/custom_ansible.sh slurm_monitoring_database
```

Continue only if the play recap reports `failed=0`. It creates `slurm_jobs`,
the `jobs` and `job_utilization` tables, and the monitoring users.

### Verify Slurm Accounting Before Validating Job Monitoring

Run this section only for Slurm job monitoring. The job exporter reads `sacct`.
Check Slurm accounting on the primary controller:

```bash
sudo systemctl is-active slurmdbd
sacct -S today --format=JobID,State,NodeList,Start,End | head
```

Expected result:

```text
active
JobID             State        NodeList               Start                 End
```

`sacct` can be empty on a new cluster. It must not return a connection or
accounting-database error. If it fails, repair Slurm accounting first:

```bash
sudo journalctl -u slurmdbd -n 100 --no-pager
sudo systemctl status slurmdbd --no-pager -l
```

Do not point `slurmdbd` at the `slurm_jobs` monitoring database. It remains
separate from the cluster's normal Slurm accounting database.

## Scenario 1: Enable Monitoring on the Controller

Use this workflow when the cluster was deployed without monitoring and no
dedicated monitoring node exists. If you enabled additional features in
Resource Manager, complete the [common post-apply
configuration](#common-post-apply-configuration) first.

### Confirm the Starting State and Set the Monitoring Host

Run these commands on the controller:

```bash
grep -E '^(cluster_monitoring|monitoring_hostname)=' /config/playbooks/inventory
awk '/^\[monitoring\]/{flag=1; next} /^\[/{flag=0} flag && NF {print}' /config/playbooks/inventory
```

The `[monitoring]` group must be empty. Set `monitoring_hostname` to the
controller hostname in both inventory files. Do not add a monitoring-group
host:

```bash
CLUSTER=$(awk -F= '/^cluster_name=/{print $2; exit}' /config/playbooks/inventory)
CONTROLLER=$(hostname -s)
sudo sed -i "s/^monitoring_hostname=.*/monitoring_hostname=${CONTROLLER}/" \
  /config/playbooks/inventory "/config/playbooks/inventory_${CLUSTER}"
```

If the `[monitoring]` group contains a host, use Scenario 2 instead.

### Create the Focused Monitoring Playbook

Do **not** run `/config/playbooks/monitoring.yml` on an existing controller.
It includes initial-node NFS and host setup.

Create `/tmp/enable_monitoring.yml` instead. It runs controller monitoring
roles only. It does not initialize managed MySQL; complete that common
configuration step first when Slurm job monitoring is enabled.

```bash
cat > /tmp/enable_monitoring.yml <<'EOF'
---
# Enable controller-hosted monitoring for an existing cluster.
# This playbook intentionally runs only monitoring-related sections from site.yml.

- name: Install controller-side exporters and OCI metrics collectors
  hosts: controller, slurm_backup
  gather_facts: true
  vars:
    compute_node: false
  pre_tasks:
    - name: Collect cluster architecture context
      ansible.builtin.import_tasks: /config/playbooks/tasks/collect_cluster_context.yml
    - name: Prepare shared 3rdparty paths
      ansible.builtin.import_tasks: /config/playbooks/tasks/prepare_thirdparty_paths.yml
  tasks:
    - name: Install metrics exporter on controller or backup
      ansible.builtin.include_role:
        name: metrics-exporter
    - name: Install OCI metrics exporters
      ansible.builtin.include_role:
        name: oci-metrics
      when: cluster_monitoring | default(false) | bool

- name: Enable Slurm job monitoring pieces when configured
  hosts: controller, slurm_backup
  gather_facts: true
  tasks:
    - name: Install Slurm monitoring services
      ansible.builtin.include_role:
        name: slurm_monitoring
      vars:
        slurm_monitoring_controller_rest_exporter_enabled: "{{ slurm_job_monitoring | default(false) | bool }}"
        slurm_monitoring_controller_job_exporter_enabled: "{{ slurm_job_monitoring | default(false) | bool }}"
        slurm_monitoring_controller_enable_db_compact: >-
          {{
            slurm_job_monitoring | default(false) | bool
            and inventory_hostname == (groups['controller'] | first)
          }}
      when:
        - cluster_monitoring | default(false) | bool
        - slurm | default(false) | bool
        - slurm_job_monitoring | default(false) | bool
        - groups['monitoring'] | length == 0

- name: Install Grafana, Prometheus, and scrape target files on controller
  hosts: controller
  gather_facts: true
  tasks:
    - name: Discover cluster nodes for Prometheus targets
      ansible.builtin.include_role:
        name: get_nodes_in_cluster
      when: cluster_monitoring | default(false) | bool
    - name: Generate Prometheus target files
      ansible.builtin.include_role:
        name: prometheus_targets
      when: cluster_monitoring | default(false) | bool
    - name: Install Grafana on controller
      ansible.builtin.include_role:
        name: grafana
      when:
        - cluster_monitoring | default(false) | bool
        - groups['monitoring'] | length == 0
    - name: Install OCI metrics Telegraf bridge
      ansible.builtin.include_role:
        name: oci-metrics-telegraf
      when:
        - cluster_monitoring | default(false) | bool
        - groups['monitoring'] | length == 0
        - (metrics_stream_ocid | default('')) | length > 0
    - name: Install Prometheus on controller
      ansible.builtin.include_role:
        name: prometheus
      when:
        - cluster_monitoring | default(false) | bool
        - groups['monitoring'] | length == 0
EOF
```

### Create the Wrapper Script

Create `/tmp/enable_monitoring.sh`. It runs the focused playbook, refreshes
exporters, then regenerates Prometheus targets.

```bash
cat > /tmp/enable_monitoring.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

source /etc/os-release
VENV="/config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci"
BASE_INVENTORY="/config/playbooks/inventory"

CLUSTER=$(awk -F= '/^cluster_name=/{print $2; exit}' "$BASE_INVENTORY")
CONTROLLER=$(awk -F= '/^controller_hostname=/{print $2; exit}' "$BASE_INVENTORY")
CLUSTER_INVENTORY="/config/playbooks/inventory_${CLUSTER}"

echo "Cluster: ${CLUSTER}"
echo "Controller: ${CONTROLLER}"
echo "Inventory: ${CLUSTER_INVENTORY}"

BACKUP="${BASE_INVENTORY}.pre-monitoring.$(date +%Y%m%d%H%M%S).bak"
cp "$BASE_INVENTORY" "$BACKUP"
echo "Inventory backup: ${BACKUP}"

# Enable controller-hosted monitoring in both inventories.
sed -i \
  -e 's/^cluster_monitoring=.*/cluster_monitoring=true/' \
  -e "s/^monitoring_hostname=.*/monitoring_hostname=${CONTROLLER}/" \
  "$BASE_INVENTORY" "$CLUSTER_INVENTORY"

grep -E '^(cluster_monitoring|monitoring_hostname)=' \
  "$BASE_INVENTORY" "$CLUSTER_INVENTORY"

MONITORING_GROUP_CONTENT=$(awk '/^\[monitoring\]/{flag=1; next} /^\[/{flag=0} flag {print}' "$CLUSTER_INVENTORY" | sed '/^[[:space:]]*$/d' || true)
if [[ -n "$MONITORING_GROUP_CONTENT" ]]; then
  echo "ERROR: [monitoring] group is not empty. This script is only for no-monitoring-node mode."
  echo "$MONITORING_GROUP_CONTENT"
  exit 1
fi

run_monitoring_playbook() {
  ANSIBLE_CONFIG=/etc/ansible/ansible.cfg \
  ANSIBLE_ROLES_PATH=/config/playbooks/roles \
  ANSIBLE_HOST_KEY_CHECKING=False \
  "$VENV/bin/ansible-playbook" \
    --private-key ~/.ssh/cluster.key \
    -i "$CLUSTER_INVENTORY" \
    /tmp/enable_monitoring.yml
}

echo "Running focused monitoring playbook on controller..."
run_monitoring_playbook

echo "Refreshing exporters on existing compute nodes..."
mgmt nodes reconfigure --fields role=compute --action ansible --playbook compute

echo "Refreshing exporters on existing login nodes, if any..."
mgmt nodes reconfigure --fields role=login --action ansible --playbook login || \
  echo "WARNING: login exporter refresh failed or no login nodes matched."

echo "Refreshing Prometheus targets after exporters were installed..."
run_monitoring_playbook

echo "Validating Grafana and Prometheus services..."
systemctl is-active grafana-server
systemctl is-active prometheus

echo "Validating health endpoints..."
curl -fsS http://localhost:3000/api/health
curl -fsS http://localhost:9090/-/ready

curl -fsS http://localhost:9090/api/v1/targets >/tmp/prometheus-targets.json
echo "Prometheus targets written to /tmp/prometheus-targets.json"
echo "Monitoring enablement workflow completed."
EOF

chmod +x /tmp/enable_monitoring.sh
```

### Run the Wrapper

Run this command on the controller:

```bash
/tmp/enable_monitoring.sh
```

The workflow is complete when the script prints:

```text
Monitoring enablement workflow completed.
```

### Validate Manually

Run these commands on the controller:

```bash
sudo systemctl is-active grafana-server
sudo systemctl is-active prometheus
curl -fsS http://localhost:3000/api/health
curl -fsS http://localhost:9090/-/ready
curl -fsS http://localhost:9090/api/v1/targets | python3 -m json.tool | less
```

At a minimum, verify the core node exporter (`:9100`) and GPU exporter
(`:9800`, where applicable) for each configured node report `up`.

### Verify Grafana Visually

Open the Grafana URL for the controller-hosted monitoring instance and confirm:

1. The provisioned `Prometheus` data source is healthy.
2. **Explore** returns the core controller, compute, and login targets for the
   `up` query. Confirm the required `:9100` and, where applicable, `:9800`
   targets are `1`.
3. A provisioned cluster dashboard displays current metrics after selecting the
   cluster and node filters.

### Roll Back the Inventory Change

The wrapper writes an inventory backup before making changes. To revert only
the inventory setting, restore that backup:

```bash
cp /config/playbooks/inventory.pre-monitoring.<timestamp>.bak /config/playbooks/inventory
CLUSTER=$(awk -F= '/^cluster_name=/{print $2; exit}' /config/playbooks/inventory)
cp /config/playbooks/inventory "/config/playbooks/inventory_${CLUSTER}"
```

Restore the matching cluster-specific backup as well. This restores inventory
values only; it does not uninstall monitoring services.

### Troubleshooting

| Symptom | Check |
| --- | --- |
| Playbook cannot find roles | Confirm `ANSIBLE_ROLES_PATH=/config/playbooks/roles` is set by the wrapper. |
| Playbook cannot SSH | Confirm `~/.ssh/cluster.key` exists for the controller user and the inventory has the controller host. |
| No compute targets | Confirm the compute reconfigure command completed, then rerun `/tmp/enable_monitoring.sh` or the focused playbook. |
| Grafana inactive | Check `sudo journalctl -u grafana-server -n 100 --no-pager`. |
| Prometheus inactive | Check `sudo journalctl -u prometheus -n 100 --no-pager`. |
| Wrong mode | Confirm `[monitoring]` is empty. This workflow is not for dedicated monitoring node mode. |

## Scenario 2: Add a Dedicated Monitoring Node

Use this workflow when the cluster was deployed without monitoring and you want
to add a new VM that will run Grafana and Prometheus. If you enabled additional
features in Resource Manager, complete the [common post-apply
configuration](#common-post-apply-configuration) before the monitoring bootstrap.
Leave `monitoring_hostname` empty until step 6.

### Assumptions

- The cluster is already deployed with monitoring disabled.
- Terraform values for the starting stack were `cluster_monitoring=false` and
  `monitoring_node=false`.
- The controller is reachable and `/config/playbooks/inventory` exists on the
  controller.
- This workflow uses a manually created VM. Do not set `monitoring_node` or its
  sizing variables.

### 1. Gather the Cluster Values

**Run on: controller**

Get the cluster SSH key and the `/config` FSS mount-target IP:

```bash
cat /config/key/public
findmnt -n -o OPTIONS /config | tr ',' '\n' | grep -E '^(addr|mountaddr)='
```

Keep the full public-key line. Record the IP after `addr=` or `mountaddr=`.
Use this IP for the `/config` mount.

### 2. Create the Monitoring VM in OCI Console

1. In the OCI Console, open **Compute > Instances > Create instance**.
2. Set the instance name to `<cluster_name>-monitoring`.
3. Select the same supported operating-system family as the controller. Use the
   corresponding login user: `ubuntu` for Ubuntu or `opc` for Oracle Linux.
4. Select an appropriately sized VM shape. A small flexible VM is sufficient
   for a functional test.
5. Under **Networking**, select the cluster VCN and match the subnet type used
   by the controller: select the **public subnet** and assign a public IP for a
   normal deployment, or select a **private subnet** with no public IP for a
   private deployment. The selected subnet must reach the controller and FSS
   mount target.
6. Under **Add SSH keys**, select **Paste public keys**. Paste the user's SSH
   public key and the exact output of `cat /config/key/public`, with each key
   on its own line. The user's key allows direct access to the monitoring VM
   when network connectivity permits; the cluster key allows the controller to
   connect during configuration.
7. Create the VM and wait for it to reach the **Running** state.

> **Expected result:** The new VM is **Running**. Record its hostname, private
> IP address, and login user.

### 3. Verify Controller Access to the Monitoring VM

**Run on: controller**

Replace the placeholder values with the values recorded in the previous step:

```bash
export CLUSTER=<cluster_name>
export MONITORING_USER=<cluster_admin_user>
export MONITORING_HOST=<monitoring_hostname>
export MONITORING_IP=<monitoring_private_ip>

ssh -i ~/.ssh/cluster.key "${MONITORING_USER}@${MONITORING_IP}" 'hostname; whoami'
```

> **Expected result:** The command prints the monitoring hostname and login
> user. If it returns `Permission denied (publickey)`, recreate or update the
> VM with the public key from `/config/key/public`.

### Switch Between the Controller and Monitoring VM

Each remaining step states where to run its commands. To connect to the
monitoring VM from the controller, run:

```bash
ssh -i ~/.ssh/cluster.key "${MONITORING_USER}@${MONITORING_IP}"
```

Run `exit` on the monitoring VM to return to the controller.

### 4. Mount `/config` on the Monitoring VM

**Run on: monitoring VM**

Install the NFS client package if it is not already present:

```bash
# Ubuntu
sudo apt-get update
sudo apt-get install -y nfs-common

# Oracle Linux
sudo dnf install -y nfs-utils
```

Set `CONFIG_FSS_IP` to the FSS mount-target IP recorded in step 1, then mount
and verify `/config` before adding it to `/etc/fstab`:

```bash
export CONFIG_FSS_IP=<fss_mount_target_ip>
sudo mkdir -p /config
sudo mount -t nfs -o nconnect=16 "${CONFIG_FSS_IP}:/config" /config
ls /config/bin/monitoring.sh
echo "${CONFIG_FSS_IP}:/config /config nfs defaults,nconnect=16 0 0" | sudo tee -a /etc/fstab
```

> **Expected result:** `/config/bin/monitoring.sh` is listed. If the mount
> fails with `Unknown host`, verify that you used the FSS mount-target IP, not
> its hostname.

### 5. Test `/home` NFS Access

**Run on: monitoring VM**

This is a temporary connectivity test only. Do not mount `/home` persistently;
the monitoring bootstrap in step 7 configures the appropriate shared `/home`
mount through Ansible.

```bash
export CONTROLLER_HOST=<controller_hostname>
hostname -I
getent ahosts "${CONTROLLER_HOST}"
showmount -e "${CONTROLLER_HOST}"
sudo mkdir -p /mnt/test-home
sudo mount -t nfs "${CONTROLLER_HOST}:/home" /mnt/test-home
ls /mnt/test-home
sudo umount /mnt/test-home
```

> **Expected result:** `showmount` lists `/home` for a CIDR covering the
> monitoring VM private IP, and the test mount succeeds.

### 6. Add the Monitoring VM to the Inventory

**Run on: controller**

```bash
sudo cp /config/playbooks/inventory /config/playbooks/inventory.before-monitoring-node
sudo cp "/config/playbooks/inventory_${CLUSTER}" "/config/playbooks/inventory_${CLUSTER}.before-monitoring-node"
sudo vi /config/playbooks/inventory
```

This step uses the `CLUSTER`, `MONITORING_HOST`, `MONITORING_IP`, and
`MONITORING_USER` values set in step 3. If you opened a new controller shell,
run the export block from step 3 first.

In `/config/playbooks/inventory`, replace the existing values in `[all:vars]`.
Do not add a second `cluster_monitoring` or `monitoring_hostname` line; the
later duplicate value can cause monitoring roles to be skipped.

The resulting monitoring-group entry and `[all:vars]` values must be:

```ini
[monitoring]
<monitoring_hostname> ansible_host=<monitoring_private_ip> ansible_user=<cluster_admin_user> role=monitoring ansible_interpreter_python_fallback=/config/venv/Ubuntu_22.04_x86_64/oci/bin/python3,/usr/bin/python3,python3

[all:vars]
cluster_monitoring=true
monitoring_hostname=<monitoring_hostname>
```

For Oracle Linux monitoring nodes, adjust the interpreter fallback to the
matching virtual environment path, for example:

```ini
ansible_interpreter_python_fallback=/config/venv/Ol_9.5_x86_64/oci/bin/python3,/usr/bin/python3,python3
```

Make the same monitoring-group and `[all:vars]` edits in
`/config/playbooks/inventory_${CLUSTER}`. Do not copy the base inventory over
the cluster-specific inventory: doing so can discard runtime inventory data.

Verify both inventory files:

```bash
grep -E '^(cluster_monitoring|monitoring_hostname)=' /config/playbooks/inventory
awk '/^\[monitoring\]/{flag=1; next} /^\[/{flag=0} flag && NF {print}' /config/playbooks/inventory

grep -E '^(cluster_monitoring|monitoring_hostname)=' "/config/playbooks/inventory_${CLUSTER}"
awk '/^\[monitoring\]/{flag=1; next} /^\[/{flag=0} flag && NF {print}' "/config/playbooks/inventory_${CLUSTER}"
```

> **Expected result:** Both inventory files show `cluster_monitoring=true` and
> the same non-empty `monitoring_hostname`. If either file still contains
> `cluster_monitoring=false` or an empty `monitoring_hostname`, correct it
> before running the bootstrap.

### 7. Run the Initial Monitoring Bootstrap

**Run on: monitoring VM**

Passing the cluster name is required because a manually created VM might not
have the OCI freeform tag `cluster_name`.

```bash
cd /config/bin
./monitoring.sh <cluster_name>
```

> **Expected result:** The play recap ends with `failed=0` and `monitoring.sh`
> exits with `rc=0`.

### 8. Refresh Exporters on Existing Nodes

**Run on: controller**

Run these commands after the initial monitoring bootstrap succeeds. Existing
compute and login nodes need their monitoring exporters installed. First,
confirm that nodes are registered with their roles:

```bash
mgmt nodes list --format tabular --columns hostname,role,status,compute_status,controller_status
```

If the compute nodes are still `starting`, have blank roles, or the command
reports `No nodes found`, wait until they register. If Slurm already shows the
compute nodes as idle, reconfigure them explicitly instead:

```bash
mgmt nodes reconfigure --nodes <compute-hostname-1>,<compute-hostname-2> \
  --action ansible --playbook compute
```

Otherwise, refresh nodes by role:

```bash
mgmt nodes reconfigure --fields role=compute --action ansible --playbook compute
mgmt nodes reconfigure --fields role=login --action ansible --playbook login
```

If the cluster has no login nodes, the login command may have nothing to
change.

> **Expected result:** Each command completes without an Ansible failure. If
> the cluster has no login nodes, the login command can report that no nodes
> were found.

### 9. Rerun Monitoring to Refresh Prometheus Targets

**Run on: monitoring VM**

Run this again after exporters have been refreshed on the existing nodes:

```bash
cd /config/bin
./monitoring.sh <cluster_name>
```

> **Expected result:** Prometheus target files are regenerated and the play
> recap ends with `failed=0`.

### 10. Validate Grafana, Prometheus, and Targets

**Run on: monitoring VM**

```bash
sudo systemctl is-active grafana-server
sudo systemctl is-active prometheus
curl -fsS http://localhost:3000/api/health
curl -fsS http://localhost:9090/-/ready
curl -fsS http://localhost:9090/api/v1/targets | python3 -m json.tool | less
```

> **Expected result:** `grafana-server` and `prometheus` are active. Grafana
> returns `database ok`. Prometheus returns `Prometheus Server is Ready`. At a
> minimum, verify the core node exporter (`:9100`) and GPU exporter (`:9800`,
> where applicable) for each configured node report `up`.

### 11. Open Grafana from Your Workstation

If ingress to TCP/3000 is intentionally configured, open
`http://<monitoring_public_ip>:3000` in a browser. Otherwise, create an SSH
tunnel through the controller from a terminal on your workstation:

```bash
ssh -N -L 33000:<monitoring_private_ip>:3000 \
  -i <controller_ssh_private_key> <cluster_admin_user>@<controller_public_ip>
```

Keep that terminal open, then open `http://localhost:33000` in a browser. In
either case, use the Grafana `admin` user and the `grafana_password` from the
Resource Manager stack's **Application Information**.

### 12. Verify Grafana Visually

In the Grafana browser session, confirm:

1. The provisioned `Prometheus` data source is healthy.
2. **Explore** returns the core controller, compute, and login targets for the
   `up` query. Confirm the required `:9100` and, where applicable, `:9800`
   targets are `1`.
3. A provisioned cluster dashboard displays current metrics after selecting the
   cluster and node filters.

Known good play recap:

```text
PLAY RECAP
localhost                  : ok=382  changed=92   unreachable=0    failed=0    skipped=185  rescued=0    ignored=1
<controller_hostname>      : ok=1    changed=0    unreachable=0    failed=0    skipped=2    rescued=0    ignored=0

Ansible succeeded!
Ansible playbook execution complete
EXIT script=monitoring.sh rc=0
```

## Validate Slurm Job Monitoring (Both Scenarios)

After the selected monitoring workflow completes, run these commands on the
controller when `slurm_job_monitoring=true`:

```bash
sudo systemctl is-active slurm-rest-exporter
sudo systemctl is-active slurm-job-exporter
curl -fsS http://localhost:9902/metrics | grep 'slurm_jobs_collected_total'
```

Both services must be `active`, and the metric must be emitted. Its value can
be zero on a new cluster with no completed jobs. Submit a short job and confirm
it is visible through `sacct` before treating a zero value as an exporter
problem.
