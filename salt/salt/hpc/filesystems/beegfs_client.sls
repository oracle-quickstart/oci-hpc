/mnt/beegfs:
  file.directory:
    - makedirs: True

sysMgmtdHost-client:
  file.line:
    - name: /etc/beegfs/beegfs-client.conf
    - content: sysMgmtdHost      = {{grains['master']}}
    - match: sysMgmtdHost
    - mode: replace

beegfs-helperd-enabled:
  service.enabled:
    - name: beegfs-helperd

beegfs-helperd-running:
  service.running:
    - name: beegfs-helperd

beegfs-client-enabled:
  service.enabled:
    - name: beegfs-client

beegfs-client-running:
  service.running:
    - name: beegfs-client