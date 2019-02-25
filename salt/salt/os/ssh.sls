/home/opc/.ssh/config: 
  file.append: 
    - text: | 
        Host *
        StrictHostKeyChecking no
        UserKnownHostsFile /dev/null
        PasswordAuthentication no
        LogLevel QUIET

/home/opc/.ssh/id_rsa: 
  file.managed:
    - user: opc
    - group: opc
    - mode: 600
    - source:
      - salt://id_rsa
  
chown opc:opc /home/opc/.ssh/config:
  cmd.run

chmod 600 /home/opc/.ssh/config: 
  cmd.run
