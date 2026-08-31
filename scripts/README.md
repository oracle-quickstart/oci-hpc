
# LDAP Data Migration Scripts for Slurm Clusters

## Overview
These scripts help migrate **LDAP data (users and groups)** from one Slurm/LDAP controller to another.  They are especially useful when **upgrading Slurm clusters** and moving LDAP data from older clusters to new ones.


---

## Scripts

### 1. `gather_ldap_data.sh`


**Usage:**
```bash
./gather_ldap_data.sh <old_controller_ip>
```
This will generate LDAP data in files — group.list and user.list — containing group and user information from the old cluster.

### 2. `push_ldap_data.sh`

**Usage:**
```bash
./push_ldap_data.sh <new_controller_ip>  [--nossh|--ssh]
```

This copies the collected LDAP data in files (group.list and user.list) to the new controller and recreates users and groups.


### 3. `enable_grafana_ldap.py`

Enable Grafana LDAP login on an existing cluster where:
- Grafana is already installed
- the Slurm controller LDAP is already working
- you want existing LDAP users to log into Grafana
- the stack was deployed before the `Enable LDAP for Grafana UI` option existed or it was left unchecked

**Usage:**
```bash
sudo ./enable_grafana_ldap.py --controller-ip <controller_private_ip>
```

**Example:**
```bash
sudo ./enable_grafana_ldap.py --controller-ip 172.16.0.210
```

The script also validates:
- `controller.cluster` hostname resolution on the Grafana host
- `/etc/grafana/ldap.toml` ownership and mode (`root:grafana`, `0640`)
- LDAP TLS hostname verification with `openssl`

If `/etc/ssl/certs/cluster-ca.crt` is missing, the script will also look for the
cluster CA in common legacy locations such as `/config/key/cluster-ca.crt` and
copy it into place automatically.

Notes:
- Run it on the Grafana host.
- If Grafana is on a monitoring node, pass the controller private IP with `--controller-ip`.
- If Grafana is on the controller node, the script can infer the local controller IP when `controller.cluster` is missing.
- If you accidentally pass a controller public IP on a monitoring node, the script will prefer an inferred private controller IP when it can determine one locally.

### 4. `disable_grafana_ldap.py`

Disable Grafana LDAP login on an existing cluster and return Grafana to local-user authentication.

**Usage:**
```bash
sudo ./disable_grafana_ldap.py
```

The script:
- sets `[auth.ldap] enabled = false`
- sets `[auth.ldap] allow_sign_up = false`
- removes `/etc/grafana/ldap.toml`
- removes the `controller.cluster` host alias from `/etc/hosts`
- restarts Grafana by default

Notes:
- Run it on the Grafana host.
- It does not disable cluster LDAP on the controller.
- It does not remove the Grafana local `admin` account.
