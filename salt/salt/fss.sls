{% if pillar['fssip'] != None %}
/mnt/fss:
  mount.mounted:
    - device: {{ pillar['fssip'] }}:/{{pillar['fss_share_name']}}
    - fstype: nfs
    - mkmnt: True
    - persist: True
    - opts:
      - defaults
{% endif %}