# DGXC Benchmarking

DGXC benchmarking is installed only when the cluster inventory enables
`dgxc_benchmarking=true`, `slurm=true`, and `pyxis=true`.

The one-time shared DGXC install must run on exactly one GPU node. First confirm
the target node exists in the Ansible inventory:

```bash
source /config/bin/setup_environment.sh
cluster_name=$(curl -fsL -H "Authorization: Bearer Oracle" \
  http://169.254.169.254/opc/v2/instance/freeformTags/cluster_name)
inventory="/config/playbooks/inventory_${cluster_name}"

$VENV_PATH/bin/ansible-inventory -i "$inventory" --graph
```

If the GPU node appears in that inventory, run the shared install from the
controller:

```bash
/config/bin/custom_ansible.sh dgxc_benchmarking \
  -e dgxc_target_hosts=<gpu-inventory-hostname> \
  -e dgxc_run_llmb_install=true
```

DGXC shell integration can be applied to existing compute nodes with:

```bash
mgmt nodes reconfigure --action ansible --playbook dgxc_benchmarking_nodes --fields role=compute
```

The shell integration installs wrappers under `/opt/dgxc-benchmarking/bin` and
an opt-in environment loader at `/opt/dgxc-benchmarking/bin/load-dgxc-env`. It
does not add DGXC commands to the default system `PATH`.

To use the DGXC wrappers in an interactive shell:

```bash
source /opt/dgxc-benchmarking/bin/load-dgxc-env
llmb-run --version
```

DGXC notes:

- `dgxc_benchmarking=true` and `pyxis=true` enable DGXC shell integration during normal controller, login, monitoring, and compute node configuration.
- `playbooks/dgxc_benchmarking.yml` must target exactly one host because it writes to shared DGXC paths under `/config/3rdparty`.
- The DGXC shared install should target a GPU node, not the controller.
- `playbooks/dgxc_benchmarking.yml` replays the generated DGXC config when `dgxc_run_llmb_install=true`.
- `playbooks/dgxc_benchmarking_nodes.yml` installs `/opt/dgxc-benchmarking/bin` wrappers and the `load-dgxc-env` loader only.
- DGXC shell integration does not install `git`, `git-lfs`, or other packages on every node.
- The same shell integration is also part of the standard controller, login, monitoring, and compute node playbooks so future nodes receive it during normal configuration when `dgxc_benchmarking=true`.
- Live `llmb-install` playback output is written to `/config/3rdparty/dgxc-benchmarking/logs/llmb-install-<node>.latest.log`.
