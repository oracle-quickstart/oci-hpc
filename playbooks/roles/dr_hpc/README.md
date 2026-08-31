# dr_hpc

Installs `oci-dr-hpc-v2` from the public OCI Object Storage bucket.

## Behavior

The role supports two metadata selection modes:

- `latest` mode (default): if shared metadata already exists under `/config/3rdparty/oci-dr-hpc-v2`, reuse that cluster version; otherwise fetch `latest.json`, cache it, and install it
- `pinned` mode: fetch `/<version>/manifest.json` and install that exact version

The role resolves the correct artifact for the current operating system and CPU
architecture, downloads it into the shared `/config/3rdparty/oci-dr-hpc-v2`
cache, installs it via the native package manager, and persists shared release
metadata for future nodes.

Supported package formats are currently:

- Ubuntu: DEB package from the `deb_ubuntu` artifact map
- Oracle Linux: RPM package from the `rpm` artifact map

## Role Layout

The role intentionally keeps a small task surface:

- `tasks/main.yml`: resolves metadata, coordinates the shared cache, checks the
  installed package version, and dispatches installation
- `tasks/ubuntu.yml`: installs the cached DEB package
- `tasks/ol.yml`: installs the cached RPM package

The cache flow uses a simple contract: if shared metadata exists, the role
trusts it. When metadata must be refreshed, one node takes the shared lock,
downloads both the OCI metadata and package, then writes the metadata file last.

There are two different operational intents:

- normal bootstrap or node-add runs with no explicit version follow the shared
  cluster metadata already cached in `/config/3rdparty/oci-dr-hpc-v2`
- admin-triggered mgmt runs with no explicit version force a refresh from
  `latest.json` and roll that version out across the selected compute nodes

## Variables

Defaults are defined in [defaults/main.yml](defaults/main.yml).

- `dr_hpc_bucket_url`: base OCI Object Storage URL
- `dr_hpc_package_name`: package name, default `oci-dr-hpc-v2`
- `dr_hpc_download_dir`: shared cache location, default `/config/3rdparty/oci-dr-hpc-v2`
- `dr_hpc_use_latest_metadata`: when `true`, use `latest.json`
- `dr_hpc_force_latest_refresh`: ignore cached shared metadata and refresh from `latest.json`
- `dr_hpc_version`: required when `dr_hpc_use_latest_metadata` is `false`
- `dr_hpc_latest_metadata_name`: metadata object name for latest mode
- `dr_hpc_release_metadata_path`: shared cluster metadata file path, derived from `dr_hpc_download_dir`
- `dr_hpc_cache_lock_path`: shared lock directory path, derived from `dr_hpc_download_dir`

## Usage

Latest mode:

```yaml
- hosts: localhost
  become: true
  roles:
    - dr_hpc
```

Pinned mode:

```yaml
- hosts: localhost
  become: true
  vars:
    dr_hpc_use_latest_metadata: false
    dr_hpc_version: "1.0.444"
  roles:
    - dr_hpc
```

Pinned mode is strict:

- if `dr_hpc_use_latest_metadata` is `false`
- and `dr_hpc_version` is empty
- the role fails immediately

## mgmt Integration

The `mgmt nodes reconfigure --action dr-hpc` workflow uses this role with two
behaviors:

- no `--version`: mgmt passes an internal force-refresh flag so the role
  refreshes the shared cache from `latest.json`
- with `--version X.Y.Z`: mgmt switches the role to pinned mode for that exact
  version

That means:

- bootstrap and node-add flows stay cluster-stable by default
- explicit sysadmin-triggered mgmt rollouts without `--version` become cluster
  upgrades to the current latest release

## Persisted Metadata

After the shared cache is populated, the role writes JSON metadata to
`dr_hpc_release_metadata_path` (default
`/config/3rdparty/oci-dr-hpc-v2/oci-dr-hpc-v2-release.json`).

This file includes:

- package name
- resolved version and release
- generated timestamp when present
- artifact map from OCI metadata

The file content is the OCI metadata response as-is. The role does not add
cluster-local fields to it.

The installed version is not stored in the shared metadata file because that
value is host-specific. Instead, the role reads it from the OS package database
on each node:

- Ubuntu: `dpkg-query`
- Oracle Linux: `rpm -q`

## Shared Cache Coordination

Nodes coordinate through a shared lock directory under `/config/3rdparty`.

- only one node refreshes metadata and downloads the package at a time
- metadata is written after the package download completes
- other nodes wait for the lock to disappear, then read the shared metadata
- default mode therefore converges new nodes on the cluster version already
  cached in `/config/3rdparty/oci-dr-hpc-v2`
- forced latest refresh mode ignores the cached metadata and repopulates the
  shared cache from OCI
