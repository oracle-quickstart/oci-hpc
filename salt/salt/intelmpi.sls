intelmpi_repo: 
  pkgrepo.managed:
    - humanname: Intel(R) MPI Library
    - baseurl: https://yum.repos.intel.com/mpi
    - enabled: 1
    - gpgcheck: 1
    - gpgkey: https://yum.repos.intel.com/mpi/setup/PUBLIC_KEY.PUB

intel-mpi-2019.1-053:
  pkg.installed