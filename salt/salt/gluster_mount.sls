
{% if 'gluster' in grains['roles'] %}

  {% set storage_servers = [] %}
  {% for item in pillar['storage_servers'].split(',') %}
    {% do storage_servers.append( item + "." + pillar['private_subnet_name']) %}
  {% endfor %}

  {% if storage_servers|length > 0 %}
mount glusterfs volume:
  mount.mounted:
    - name: /mnt/gluster
    - device: {{ storage_servers|join(',') }}:/gfs
    - fstype: glusterfs
    - opts: _netdev,rw,defaults,direct-io-mode=disable
    - mkmnt: True
    - persist: True
    - dump: 0
    - pass_num: 0
    - device_name_regex:
      - ({{ storage_servers|join('|') }}):/gfs
    - retry:
        attempts: 10
        until: True
        interval: 60
        splay: 10

/mnt/gluster:
  file.directory:
    - user: opc
    - group: opc

    {% endif %}

{% endif %}