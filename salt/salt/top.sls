base: 
    '*': 
        - update
        - selinux
        - files
        - firewall
        - iscsi
        - software
        - fss
        - partitions
        - nfs
    'G@roles:gluster':
        - gluster
    'P@roles:(pbspro_server|pbspro_execution)':
        - pbspro
    'G@roles:intelmpi':
        - intelmpi