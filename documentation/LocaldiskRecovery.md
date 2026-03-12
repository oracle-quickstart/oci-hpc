# Local Disk (NVMe RAID) Management

## Overview

Compute nodes with multiple NVMe drives have them configured as a RAID array mounted at `/mnt/localdisk`. This document covers how to recover or reconfigure the local disk RAID array.

## Architecture

The `localdisk` role supports two modes:

| Mode | Variable | Behavior |
|------|----------|----------|
| Setup | `localdisk_recover: false` | Idempotent setup, skips if array exists |
| Recovery | `localdisk_recover: true` | Destructive recovery, recreates array |

A wrapper playbook (`recover_localdisk.yml`) provides CLI compatibility for recovery operations.

## Actions

| Action | Description | Data Loss |
|--------|-------------|-----------|
| `localdisk-recover` | Recovers a broken/corrupted array using the same RAID level | Yes (if recovery needed) |
| `localdisk-raid0` | Recreates array as RAID0 (striped, maximum performance) | Yes |
| `localdisk-raid10` | Recreates array as RAID10 (mirrored+striped, fault tolerant) | Yes |

## RAID Levels

| Level | Description | Fault Tolerance | Capacity |
|-------|-------------|-----------------|----------|
| RAID0 | Striped across all drives | None - any drive failure destroys array | 100% of total |
| RAID10 | Mirrored pairs, then striped | Can survive drive failures | 50% of total |

## Usage

### Recovering a broken array

If `/mnt/localdisk` is unavailable or corrupted:

```bash
mgmt nodes reconfigure --nodes <node> --action localdisk-recover
```

This will:
- Auto-detect the previous RAID level from `/etc/mdadm/mdadm.conf`
- Skip nodes where the filesystem is already healthy
- Recreate the array with the same RAID level

Examples:
```bash
# Single node
mgmt nodes reconfigure --nodes gpu-1770 --action localdisk-recover

# Multiple nodes
mgmt nodes reconfigure --nodes gpu-[1770,7852] --action localdisk-recover
```

### Changing RAID level

To recreate the array with a specific RAID level:

```bash
# Recreate as RAID0 (maximum performance, no fault tolerance)
mgmt nodes reconfigure --nodes gpu-1770 --action localdisk-raid0

# Recreate as RAID10 (fault tolerant)
mgmt nodes reconfigure --nodes gpu-1770 --action localdisk-raid10
```

> [!WARNING]
> These actions will destroy all data on the local NVMe drives, even if the filesystem is currently healthy.

### Running directly on a node

You can also run the recovery playbook directly on a compute node:

```bash
# Auto-detect RAID level (recover mode)
ansible-playbook /config/playbooks/recover_localdisk.yml

# Force RAID0
ansible-playbook /config/playbooks/recover_localdisk.yml -e redundancy=false -e force_recovery=true

# Force RAID10
ansible-playbook /config/playbooks/recover_localdisk.yml -e redundancy=true -e force_recovery=true
```

### Using the role directly

You can also invoke recovery mode by including the role with the appropriate variables:

```yaml
- hosts: target_nodes
  become: true
  roles:
    - role: localdisk
      localdisk_recover: true
      nvme_path: /mnt/localdisk
      # redundancy: auto  # or true (RAID10) / false (RAID0)
      # force_recovery: false
```

## Playbook Options

| Option | Values | Default | Description |
|--------|--------|---------|-------------|
| `localdisk_recover` | `true`, `false` | `false` | Enable recovery mode (destructive) |
| `redundancy` | `auto`, `true`, `false` | `auto` | RAID level: auto=detect from mdadm.conf, true=RAID10, false=RAID0 |
| `force_recovery` | `true`, `false` | `false` | Force recovery even if filesystem is healthy |
| `nvme_path` | path | `/scratch` | Mount path for the RAID array |

## Diagnosing Issues

### Check if localdisk is mounted
```bash
df -h /mnt/localdisk
mountpoint /mnt/localdisk
```

### Check RAID array status
```bash
cat /proc/mdstat
mdadm --detail /dev/md0
```

### Check for I/O errors
```bash
dmesg | grep -i -E "md0|nvme.*error|xfs.*error"
```

### Check NVMe health (if nvme-cli installed)
```bash
nvme smart-log /dev/nvme0n1
```

## When to Use Each Action

| Symptom | Recommended Action |
|---------|-------------------|
| `/mnt/localdisk` not in `df -h` | `localdisk-recover` |
| Mount errors or I/O errors | `localdisk-recover` |
| Array shows inactive in `/proc/mdstat` | `localdisk-recover` |
| Want to change RAID level | `localdisk-raid0` or `localdisk-raid10` |
| Node reprovisioned, need to set up disk | `localdisk-raid0` or `localdisk-raid10` |

## Logs

Recovery logs are available at:
```
/config/logs/<hostname>.log
```
