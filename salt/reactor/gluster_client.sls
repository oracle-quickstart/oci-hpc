gluster_mount:
  local.state.sls:
    - tgt: 'G@roles:gluster and not G@roles:storage'
    - tgt_type: 'compound'
    - queue: True
    - args:
      - mods: gluster_mount