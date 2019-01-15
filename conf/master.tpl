#cloud-config
write_files:
    - encoding: b64
      content: ICAgICAgYC0vKysrKysrKysrKysrKysrKysvLS5gCiAgIGAvc3l5eXl5eXl5eXl5eXl5eXl5eXl5eXl5cy8uCiAgOnl5eXlvLy0uLi4uLi4uLi4uLi4uLi4tL295eXl5LwogL3l5eXMtICAgICAgICAgICAgICAgICAgICAgLm95eXkrCi55eXl5YCAgICAgICAgICAgICAgICAgICAgICAgYHN5eXktCjp5eXlvICAgICAgICAgICAgICAgICAgICAgICAgIC95eXkvIE9yYWNsZSBDbG91ZCBIUEMgY2x1c3RlciBkZW1vCi55eXl5YCAgICAgICAgICAgICAgICAgICAgICAgYHN5eXktIGh0dHBzOi8vZ2l0aHViLmNvbS9vY2ktaHBjL29jaS1ocGMtdGVycmFmb3JtLWFyY2gKIC95eXlzLiAgICAgICAgICAgICAgICAgICAgIC5veXl5byAgCiAgL3l5eXlvOi0uLi4uLi4uLi4uLi4uLi4tOm95eXl5L2AKICAgYC9zeXl5eXl5eXl5eXl5eXl5eXl5eXl5eXlzKy4KICAgICBgLjovK29vb29vb29vb29vb29vbysvOi5gCg==
      path: /etc/motd 

runcmd:
    - mkdir -p /srv/
    - curl -L ${par_url} -o salt.zip
    - unzip salt.zip -d /srv/
    - curl -L https://bootstrap.saltstack.com -o install_salt.sh
    - sudo sh install_salt.sh -X -P -M -A ${master_address} -J '{"auto_accept":true,"file_roots":{"base":["/srv/salt/"]},"pillar_roots":{"base":["/srv/pillar"]},"presence_events":true,"reactor":[{"salt/minion/*/start":["/srv/reactor/sync.sls","/srv/reactor/start.sls"]},{"salt/state_result/*/gluster/installed":["/srv/reactor/gluster_client.sls"]},{"salt/state_result/*/pbs/started":["/srv/reactor/pbs.sls"]},{"salt/presence/present":["/srv/reactor/presence.sls"]}]}' -j '{"autosign_grains":["server_id"],"conf_file":"/etc/salt/minion","default_include":"minion.d/*.conf","file_roots":{"base":["/srv/salt/"]},"grains":{"roles":${role}},"pillar_roots":{"base":["/srv/pillar"]},"pki_dir":"/etc/salt/pki/minion","beacons":{"status":[{"interval":10}]}}'
    - sudo systemctl start salt-master
    - sudo systemctl start salt-minion