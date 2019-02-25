mariadb-server:
  - pkg.installed

enable_mariadb_service:
  - service.enabled:
    - name: mariadb

start_mariadb_service: 
  - service.running: 
    - name: mariadb

