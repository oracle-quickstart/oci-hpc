/etc/security/limits.conf:
  file.append: 
    - text: | 
        *               hard    memlock         unlimited
        *               soft    memlock         unlimited
        *               hard    nofile          65535
        *               soft    nofile          65535

#/home/opc/.bashrc:
#  file.append: 
#    - text: 
#        - export WCOLL=/home/$MYUSER/hostfile
#        - export PATH=/opt/intel/compilers_and_libraries_2018.1.163/linux/mpi/intel64/bin:$PATH
#        - export I_MPI_ROOT=/opt/intel/compilers_and_libraries_2018.1.163/linux/mpi
#        - export MPI_ROOT=/opt/intel/compilers_and_libraries_2018.1.163/linux/mpi
#        - export I_MPI_FABRICS=tcp

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
  
#/home/opc/bin: 
#  file.directory:
#    - user: opc
#    - group: opc
#    - mode: 755

chown opc:opc /home/opc/.ssh/config:
  cmd.run

chmod 600 /home/opc/.ssh/config: 
  cmd.run
