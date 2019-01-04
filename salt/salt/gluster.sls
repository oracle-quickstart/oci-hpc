{% if grains['host'] is match ('gluster*') %}

glusterd_enabled:
  service.enabled:
    - name: glusterd

glusterd_running:
  service.running:
    - name: glusterd

/mnt/lvm/brick1:
  file.directory:
    - makedirs: True

{% endif %}

{% if grains['host'] is match ('gluster-1*') %}
peer-clusters:
  glusterfs.peered:
    - names:
    {% set domain = grains['domain'] %}
    {% for server in pillar['gluster_servers'].split(',') %}
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
    {% for server in pillar['gluster_servers'].split(',') %}
      - {{ server }}.{{ domain }}:/mnt/lvm/brick1
    {% endfor %}
    - start: True
    - retry:
        attempts: 5
        until: True
        interval: 10
        splay: 10

{% endif %}

{% set gluster_servers = [] %}
{% for item in pillar['gluster_servers'].split(',') %}
{% do gluster_servers.append( item + "." + pillar['private_subnet_name']) %}
{% endfor %}

mount glusterfs volume:
  mount.mounted:
    - name: /mnt/gluster
    - device: {{ gluster_servers|join(',') }}:/gfs
    - fstype: glusterfs
    - opts: _netdev,rw,defaults,direct-io-mode=disable
    - mkmnt: True
    - persist: True
    - dump: 0
    - pass_num: 0
    - device_name_regex:
      - ({{ gluster_servers|join('|') }}):/gfs
    - retry:
        attempts: 10
        until: True
        interval: 60
        splay: 10