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
{% set storage_servers = pillar['storage_servers'].split(',') %}

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
    - fire_event: gluster/installed
  {% endif %}
{% endif %}