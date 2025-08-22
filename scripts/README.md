
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


