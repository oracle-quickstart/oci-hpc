base: 
    '*': 
        - os.update
        - os.selinux
        - os.firewall
        - os.software
        - os.limits
        - os.iscsi
        - os.ssh
        - hpc.filesystems.fss
        - hpc.filesystems.headnode_nfs
    'G@roles:intelmpi':
        - hpc.libraries.intelmpi
    'G@roles:openmpi':
        - hpc.libraries.openmpi
    'I@storage_type:beegfs':
        - hpc.filesystems.beegfs
    'I@storage_type:gluster':
        - hpc.filesystems.gluster
    'Groles:docker':
        - software.docker
 
