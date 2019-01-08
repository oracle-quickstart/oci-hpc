{% set disks = [] %}
{% for disk in grains['SSDs'] if disk is match('nvme*') %}
  {% do disks.append(disk) %}
{% endfor %}

{% if disks != [] and 'gluster' in grains['roles'] %}
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

sync_custom_modules:
  module.run:
      - name: saltutil.sync_all
      - refresh: True

{% if 'sdb' in grains['disks'] and 'master' in grains['roles'] %}
/dev/sdb:
  blockdev.formatted:
  - fs_type: xfs
  - require: 
    - sync_custom_modules

/mnt/share:
  mount.mounted:
    - device: /dev/sdb
    - fstype: xfs
    - mkmnt: True
    - persist: True
    - opts:
      - defaults
    - require: 
      - /dev/sdb

{% elif 'master' in grains['roles'] %}

/mnt/share:
  file.directory:
    - mode: 755
    - makedirs: True

{% endif %}