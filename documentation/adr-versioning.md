# Centralize Package Version Definitions for the SLURM Stack

## Context and Problem Statement

The SLURM stack currently defines and installs system packages and Python
packages from multiple places. This spreads package ownership across Ansible
roles and requirements files, creates repeated package manager calls, makes
version constraints harder to audit, and obscures the full set of dependencies
layered onto the base image.

How should the SLURM stack define package dependencies so that system packages,
optional role dependencies, and Python requirements all use one authoritative
source of package names and versions?

## Considered Options

* Define all package names and versions in one centralized manifest
* Define system package versions in an Ansible manifest and Python package
  versions in `requirements.txt`
* Define package names and versions in the `packages` Ansible role
* Keep package installation and version definitions in each consuming role

## Decision Outcome

Chosen option: "Define all package names and versions in one centralized
manifest", because the stack needs one authoritative package/version source for
system packages, optional dependencies, and Python packages.

The SLURM stack will maintain a centralized package manifest containing package
names, package managers, version constraints, and enough metadata to
distinguish unconditional, optional, system, and Python dependencies.

During Ansible fact discovery, this manifest will be loaded and exposed as
global variables and/or facts. Roles will consume those variables when
installing packages or checking versions.

The same manifest will also generate Python requirements files, including the
short `requirements.txt` installed into the existing virtual environment
structure. Generated files must not become independent sources of truth;
updates happen in the manifest first, then generated artifacts are refreshed.

Unconditional system packages will be installed through the `packages` role in
a single package manager invocation. Optional or gated dependencies will keep
their existing role-level conditions, but their package names and versions will
also come from the manifest.

### Consequences

* Good, because package names and versions have one authoritative source.
* Good, because system packages, optional dependencies, and Python requirements
  can be audited together.
* Good, because generated `requirements.txt` files cannot drift silently from
  the intended package versions.
* Good, because package metadata is globally available during role execution.
* Good, because repeated package manager calls are reduced while keeping
  install behavior in the existing roles.
* Good, because the manifest can support automated version upgrades,
  out-of-date alerts, and a software BOM.
* Bad, because the manifest format must support both OS package manager
  semantics and Python requirement semantics.
* Bad, because generation and validation tooling is needed for derived files
  such as `requirements.txt`.
* Bad, because roles must stop defining package versions locally and instead
  consume shared variables or facts.
