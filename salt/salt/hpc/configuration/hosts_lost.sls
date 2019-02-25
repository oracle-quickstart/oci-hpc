{% for host in pillar['hosts'] %}
  {% set hostname = host.split('.')[0] %}

{{ hostname }}:
  host.absent:
    - names:
      - {{ host }}
      - {{ hostname }}

{% endfor %}