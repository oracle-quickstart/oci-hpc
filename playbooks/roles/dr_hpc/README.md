# dr_hpc

Installs `oci-dr-hpc-v2` using the Ubuntu or Oracle Linux source in
`playbooks/versions.yaml`. The fact finder expands the pinned version and
architecture into `oci_versions.dr_hpc.url` and `.cache`.

## Installation

Bootstrap, node-add, and direct playbook runs use the manifest pin without
querying release metadata. Both package formats use amd64/arm64 filenames;
the templates currently select packaging release 1.

The role has two tasks: cache the package through `safe_cache`, then install
it through `safe_yum`. The shared installer selects APT or DNF and handles
package-manager locking and retries. Repository metadata refresh is disabled
for this cached-package installation; RPM signature checking remains disabled.

There are no role-local defaults, package queries, or version comparisons.
An already-installed matching version is unchanged. When a newer version is
installed, Ubuntu rejects the older DEB, whereas DNF skips it. Neither path
forces a downgrade. The old role-specific variables are no longer used.

## Updating through mgmt

```bash
# Resolve latest.json, persist the version, then reconfigure selected nodes.
mgmt nodes reconfigure --action dr-hpc --nodes 'compute[1-4]'

# Persist an explicit version without querying latest.json.
mgmt nodes reconfigure --action dr-hpc --version 1.0.704 --nodes 'compute[1-4]'
```

Both commands update the Ubuntu and Oracle Linux pins in the shared
`/config/playbooks/versions.yaml` before starting Ansible. This changes the
version used by subsequent provisioning throughout the shared deployment, not
just the selected nodes. The caller needs write access to the manifest and
its directory.

The Python helper resolves `../latest.json` relative to the package URL:
packages live under a version directory, while latest metadata lives at the
bucket root. It returns the metadata's version string. Manifest comments and
formatting are preserved.

A file lock serializes mgmt Dr HPC rollouts; concurrent requests fail clearly.
Metadata or manifest-write failures prevent the playbook from starting.
Installation failures leave the selected pin in place for retry.

## Shared cache

The generated cache path includes the architecture and versioned filename.
`safe_cache` coordinates each destination using `<destination>.lock`: only
the owner downloads, waiters verify the result, and the owner releases its
lock even on failure. Waiters time out after ten minutes. If a process dies
and leaves a stale lock, verify its owner is no longer running before removing
that specific lock directory.

Old packages and metadata under `/config/3rdparty/oci-dr-hpc-v2` are left
untouched but are no longer consulted.
