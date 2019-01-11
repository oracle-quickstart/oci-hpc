slurm_packages:
  pkg.installed:
    - pkgs: 
      - rpm-build 
      - gcc 
      - openssl 
      - openssl-devel 
      - libssh2-devel 
      - pam-devel 
      - numactl 
      - numactl-devel 
      - hwloc 
      - hwloc-devel 
      - lua 
      - lua-devel 
      - readline-devel 
      - rrdtool-devel 
      - ncurses-devel 
      - gtk2-devel 
      - man2html 
      - infiniband-diags 
      - libibumad 
      - perl-Switch 
      - perl-ExtUtils-MakeMaker
      - mariadb-server 
      - mariadb-devel

slurm_source: 
  archive.extracted:
    - name: /var/tmp/slurm-18.08.4
    - source: https://download.schedmd.com/slurm/slurm-18.08.4.tar.bz2
    - source_hash: md5=75c76328159def203133505def7a99a6
    - user: opc
    - group: opc

slurm_rpm: 
  pkgbuild.built:
    - spec: /var/tmp/slurm-18.08.4/slurm-18.08.4/slurm.spec
    - dest_dir: /var/tmp/slurm-18.08.4/binary/