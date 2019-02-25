hosts_lost:
  local.state.apply:
    - tgt: '*'
    - args:
      - mods: hpc.configuration.hosts_lost
      - pillar:
          hosts: {{ data['lost'] }}