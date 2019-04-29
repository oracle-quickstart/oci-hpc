install_software:
  pkg.installed:
    - pkgs:
      - wpa_supplicant

{% set keys = grains['identity'] %}

wpas_interfaces:
  file.line:
    - name: /etc/sysconfig/wpa_supplicant
    - mode: replace
    - content: INTERFACES="-ienp94s0f0"
    - match: INTERFACES

wpas_drivers:
  file.line:
    - name: /etc/sysconfig/wpa_supplicant
    - mode: replace
    - content: DRIVERS="-Dwired"
    - match: DRIVERS

wpas_other:
  file.line:
    - name: /etc/sysconfig/wpa_supplicant
    - mode: replace
    - content: OTHER_ARGS="-t -P /var/run/wpa_supplicant.pid"
    - match: OTHER_ARGS

wpas_ctrl_interface:
  file.line:
    - name: /etc/wpa_supplicant/wpa_supplicant.conf
    - mode: replace
    - content: ctrl_interface=/var/run/wpa_supplicant
    - match: ctrl_interface=*

wpas_ctrl_interface_group:
  file.line:
    - name: /etc/wpa_supplicant/wpa_supplicant.conf
    - mode: replace
    - content: ctrl_interface_group=wheel
    - match: ctrl_interface_group=*

wpas_network_config:
  file.blockreplace:
    - name: /etc/wpa_supplicant/wpa_supplicant.conf
    - marker_start: "# -- DO NOT EDIT START --"
    - marker_end: "# -- DO NOT EDIT END --"
    - content: |
        network={
            fragment_size=1024
            key_mgmt=IEEE8021X
            eap=TLS
            private_key_passwd="hic sunt leones"
            private_key="/etc/wpa_supplicant/certs_bundle.pfx"
            identity="{{ grains['fqdn'] }}-{{ grains['oci_instance']['id'] }}"
            eapol_flags=0
        }
    - append_if_not_found: True
    - show_changes: True