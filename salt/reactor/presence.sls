hosts_present:
  local.state.apply:
    - tgt: '*'
    - args:
      - mods: hosts_present
      - pillar:
          hosts: {{ data['present'] }}