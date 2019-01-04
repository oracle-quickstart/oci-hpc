python2-pip:
  pkg.installed

docker:
  pip.installed:
    - name: docker
    - reload_modules: True
    - require:
      - pkg: python2-pip

