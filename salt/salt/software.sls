install_packages:
  pkg.installed:
    - enablerepo: ol7_gluster312
    - pkgs:
      - pdsh
      - stress
      - axel
      - screen
      - golang
      - sshpass
      - nmap
      - htop
      - screen
      - git
      - psmisc
      - axel
      - gcc
      - libffi-devel
      - python-devel
      - openssl-devel
      - mariadb
      - python2-pip
      - docker-engine
      - python2-gluster
      - glusterfs
      - glusterfs-cli
      - glusterfs-fuse
      - glusterfs-server

Development Tools:
  pkg.group_installed
