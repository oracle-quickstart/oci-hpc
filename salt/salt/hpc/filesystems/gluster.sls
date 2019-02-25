install_packages:
  pkg.installed:
    - enablerepo: ol7_gluster312
    - pkgs:
      - python2-gluster
      - glusterfs
      - glusterfs-cli
      - glusterfs-fuse
      {% if 'storage' in grains['roles'] %}
      - glusterfs-server
      {% endif %}

{% set disks = [] %}
{% for disk in grains['SSDs'] if disk is match('nvme*') %}
  {% do disks.append(disk) %}
{% endfor %}

{% if disks != [] and 'storage' in grains['roles'] and grains['storage_type'] == 'gluster' %}
{# role is gluster and nvme disks detected #}

  {% for disk in disks %}
/dev/{{ disk }}:
  lvm.pv_present
  {% endfor %}

gfs_vg:
  lvm.vg_present:
    - devices:
  {% for disk in disks %}
      - /dev/{{ disk }}
  {% endfor %}

gfs_data:
  lvm.lv_present:
    - vgname: gfs_vg
    - extents: +100%FREE
    - stripes: {{disks|length}}
    - require:
      - gfs_vg

/dev/dm-0:
  blockdev.formatted:
    - fs_type: xfs
    - require:
      - gfs_data

/mnt/lvm:
  mount.mounted:
    - device: /dev/dm-0
    - fstype: xfs
    - persist: True
    - mkmnt: True

{% endif %}

{% if 'storage' in grains['roles'] and grains['storage_type'] == 'gluster'}

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
        attempts: 15
        until: True
        interval: 30
    - fire_event: gluster/installed
  {% endif %}
{% endif %}