tick_install: 
  pkg.installed: 
    - sources: 
        - telegraf: https://dl.influxdata.com/telegraf/releases/telegraf-1.9.2-1.x86_64.rpm
{% if 'master' in grains['roles'] %}
        - influxdb: https://dl.influxdata.com/influxdb/releases/influxdb-1.7.2.x86_64.rpm
        - chronograf: https://dl.influxdata.com/chronograf/releases/chronograf-1.7.5.x86_64.rpm
{% endif %}

{% if 'master' in grains['roles'] %}

influxdb:
  service.running:
    - enable: True
