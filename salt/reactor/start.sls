add_minion_to_list: 
  local.state.sls:
    - tgt: 'headnode*'
    - args: 
      - mods: 'hosts_file'