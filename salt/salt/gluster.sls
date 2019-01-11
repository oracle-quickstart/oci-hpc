{% if 'gluster' in grains['roles'] and 'storage' in grains['roles'] %}

glusterd_enabled:
  service.enabled:
    - name: glusterd

glusterd_running:
  service.running:
    - name: glusterd

/mnt/lvm/brick1:
  file.directory:
    - makedirs: True
{% set storage_servers = pillar['storage'].split(',') %}

{% if grains['host'] is match storage_servers[0] %}
peer-clusters:
  glusterfs.peered:
    - names:
    {% set domain = grains['domain'] %}
    {% for server in storage_servers %}
      - {{ server }}.{{ domain }}
    {% endfor %}
    - retry:
        attempts: 5
        until: True
        interval: 10
        splay: 10

gfs:
  glusterfs.volume_present:
    - bricks:
    {% set domain = grains['domain'] %}
    {% for server in storage_servers %}
      - {{ server }}.{{ domain }}:/mnt/lvm/brick1
    {% endfor %}
    - start: True
    - retry:
        attempts: 5
        until: True
        interval: 10
        splay: 10
  {% endif %}
{% endif %}

{% if 'gluster' in grains['roles'] %}

  {% set storage_servers = [] %}
  {% for item in pillar['storage'].split(',') %}
    {% do storage_servers.append( item + "." + pillar['private_subnet_name']) %}
  {% endfor %}

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