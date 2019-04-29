install_packages:
  pkg.installed:
    - pkgs:
      - pdsh
      - stress
      - axel
      - screen
      - golang
      - sshpass
      - nmap
      - htop
      - git
      - psmisc
      - axel
      - gcc
      - libffi-devel
      - python-devel
      - openssl-devel
      - python2-pip
      - tmux

Development Tools:
  pkg.group_installed
