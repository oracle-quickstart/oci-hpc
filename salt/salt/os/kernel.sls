install-latest-kernel:
  kernel.latest_installed: []

boot-latest-kernel:
  kernel.latest_wait:
    - listen:
      - kernel: install-latest-kernel