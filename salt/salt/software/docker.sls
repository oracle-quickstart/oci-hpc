install_docker:
  pkg.installed:
    - enablerepo: ol7_addons
    - pkgs:
      - docker-engine
      - docker-cli
