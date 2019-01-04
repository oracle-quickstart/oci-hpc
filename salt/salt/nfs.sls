{% if grains['host'] is match ('headnode*') %}

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

/mnt/share:
  file.directory:
    - mode: 755
    - makedirs: True

add_simple_export:
  nfs_export.present:
    - name:     '/mnt/share/'
    - hosts:    {{ pillar['vcn_cidr'] }}
    - options:
      - 'rw'

{% else %}

/mnt/share/:
  mount.mounted:
    - device: {{ grains['master'] }}:/mnt/share/
    - fstype: nfs
    - mkmnt: True
    - persist: True
    - opts:
      - defaults

{% endif %}

