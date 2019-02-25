beegfs_client:
  local.state.sls:
    - tgt: '*'
    - queue: True
    - args:
      - mods: hpc.filesystems.beegfs_client