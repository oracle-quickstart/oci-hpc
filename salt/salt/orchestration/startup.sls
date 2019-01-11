saltutil.sync_all:
  salt.function:
    - tgt: '*'
    - reload_modules: True

saltutil.refresh_pillar:
  salt.function:
    - tgt: '*'

mine.update:
  salt.function:
    - tgt: '*'

highstate_run:
  salt.state:
    - tgt: '*'
    - highstate: True