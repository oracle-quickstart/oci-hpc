{% for host in pillar['hosts'] %}
  {% set hostname = host.split('.')[0] %}

{{ hostname }}:
  host.present:
    - ip: {{ salt['dnsutil.A'](host)[0] }}
    - names:
      - {{ host }}
      - {{ hostname }}

{% endfor %}