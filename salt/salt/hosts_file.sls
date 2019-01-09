mine.update:
  module.run

{% if 'master' in grains['roles'] %}
  {% set minions = salt.saltutil.runner('mine.get',
                tgt='*',
                fun='network.get_fqdn',
                tgt_type='glob') %}
  {% set minions_compute = salt.saltutil.runner('mine.get',
                tgt='compute-*',
                fun='network.get_fqdn',
                tgt_type='glob') %}

  {% set minions_gluster = salt.saltutil.runner('mine.get',
                tgt='gluster-*',
                fun='network.get_fqdn',
                tgt_type='glob') %}

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

/mnt/share/hosts.gluster:
  file.managed:
    - contents:
  {% for ip in minions_gluster %}
      - {{ ip }}
  {% endfor %}
{% endif %}