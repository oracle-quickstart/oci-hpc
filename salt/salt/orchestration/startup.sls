{% set data = salt.pillar.get('event_data') %}

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

highstate:
  salt.state:
    - queue: True
    - tgt: {{ data.id }}
    - highstate: True