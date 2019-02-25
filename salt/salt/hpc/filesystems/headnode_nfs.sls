{% if 'sdb' in grains['disks'] and 'master' in grains['roles'] %}
/dev/sdb:
  blockdev.formatted:
  - fs_type: xfs

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

{% if 'master' in grains['roles'] %}

rpcbind_enabled:
  service.enabled:
    - name: rpcbind

rpcbind_running:
  service.running:
    - name: rpcbind

nfs_enabled:
  service.enabled:
    - name: nfs-server

nfs_running:
  service.running:
    - name: nfs-server

nfslock_enabled:
  service.enabled:
    - name: nfs-lock

nfslock_running:
  service.running:
    - name: nfs-lock

nfsidmap_enabled:
  service.enabled:
    - name: nfs-idmap

nfsidmap_running:
  service.running:
    - name: nfs-idmap

add_simple_export:
  nfs_export.present:
    - name:     '/mnt/share/'
    - hosts:    {{ pillar['vcn_cidr'] }}
    - options:
      - 'rw'

{% else %}

mount_share:
  mount.mounted:
    - name: /mnt/share
    - device: {{ grains['master'] }}:/mnt/share/
    - fstype: nfs
    - mkmnt: True
    - persist: True
    - opts:
      - defaults

{% endif %}

share_permissions:
  file.directory:
    - name: /mnt/share
    - user: opc
    - group: opc