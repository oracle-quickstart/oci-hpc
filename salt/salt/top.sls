base: 
    '*': 
        - update
        - selinux
        - files
        - firewall
        - iscsi
        - software
        - pip
        - fss
        - partitions
        - nfs
    'G@roles:gluster':
        - gluster
    'G@roles:master':
        - hosts_file
    'G@roles:(pbspro_server|pbspro_execution)':
        - pbspro
    'G@roles:intelmpi':
        - intelmpi