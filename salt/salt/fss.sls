{% if pillar['fssip'] != None %}
fss mount:
  mount.mounted:
    - name: /mnt/fss
    - device: {{ pillar['fssip'] }}:/{{pillar['fss_share_name']}}
    - fstype: nfs
    - mkmnt: True
    - persist: True
    - opts:
      - defaults
{% endif %}

/mnt/fss:
  file.directory:
    - user: opc
    - group: opc