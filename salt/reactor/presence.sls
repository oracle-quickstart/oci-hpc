hosts_present:
  local.state.apply:
    - tgt: '*'
    - args:
      - mods: hpc.configuration.hosts_present
      - pillar:
          hosts: {{ data['present'] }}