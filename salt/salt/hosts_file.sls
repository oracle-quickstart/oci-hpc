{% if 'master' in grains['roles'] %}
  {% set minions = salt.saltutil.runner('mine.get',
                tgt='*',
                fun='network.get_fqdn',
                tgt_type='glob') %}
  {% set minions_compute = salt.saltutil.runner('mine.get',
                tgt='roles:compute',
                fun='network.get_fqdn',
                tgt_type='grain') %}
  {% set minions_storage = salt.saltutil.runner('mine.get',
                tgt='roles:storage',
                fun='network.get_fqdn',
                tgt_type='grain') %}

/mnt/share/hosts:
  file.managed:
    - contents:
  {% for ip in minions %}
      - {{ ip }}
  {% endfor %}

/mnt/share/hosts.compute:
  file.managed:
    - contents:
  {% for ip in minions_compute %}
      - {{ ip }}
  {% endfor %}

/mnt/share/hosts.storage:
  file.managed:
    - contents:
  {% for ip in minions_storage %}
      - {{ ip }}
  {% endfor %}
{% endif %}