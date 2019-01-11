gluster_mount:
  local.state.apply:
    - tgt: 'roles:gluster'
    - tgt_type: 'grain'