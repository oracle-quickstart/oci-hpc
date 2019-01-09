psxe_repo: 
  pkgrepo.managed:
    - humanname: Intel(R) Parallel Studio XE 2018 runtime
    - baseurl: https://yum.repos.intel.com/2018
    - enabled: 1
    - gpgcheck: 1
    - gpgkey: https://yum.repos.intel.com/2018/setup/RPM-GPG-KEY-intel-psxe-runtime-2018

intel-mpi-runtime-64bit:
  pkg.installed