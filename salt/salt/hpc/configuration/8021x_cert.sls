cert_schedule:
  schedule.present:
    - function: state.sls
    - job_args:
      - hpc.cluster.configuration.8021x_cert
    - seconds: 3600
    - splay: 10

wpa_cert.generate_pfx:
  module.run

wpa_supplicant:
  service:
    - running
    - watch:
      - module: wpa_cert.generate_pfx