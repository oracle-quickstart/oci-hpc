add_node:
  local.cmd.run:
    - tgt: 'G@roles:master'
    - tgt_type: 'compound'
    - arg:
      - /opt/pbs/bin/qmgr -c "create node {{ data['id'] }}"