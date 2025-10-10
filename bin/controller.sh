#!/bin/bash
#
# Cluster init configuration script
#

# wait for cloud-init completion on the controller host
execution=1
ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
sudo cloud-init status --wait

set -euo pipefail

source /etc/os-release

# Base working dir
if [ ! -d /opt/oci-hpc ] ; then
  sudo mkdir -p /opt/oci-hpc
fi
if [ "${ID}" = "ubuntu" ]; then
  sudo chown -R ubuntu:ubuntu /opt/
else
  sudo chown -R opc:opc /opt/
fi

# Distro helpers
vid="$(echo "${VERSION}" | awk -F. '{print $1}')"
if [ "${ID}" = "ol" ]; then
  if [ "${vid}" = "7" ]; then
    repo="ol7_developer_EPEL"
    sudo osms unregister || true
  elif [ "${vid}" = "8" ]; then
    repo="ol8_developer_EPEL"
    sudo osms unregister || true
  elif [ "${vid}" = "9" ]; then
    repo="ol9_developer_EPEL"
  fi
elif [ "${ID}" = "centos" ]; then
  repo="epel"
fi

# UV layout
export UV_INSTALL_DIR=/config/venv/${ID^}_${VERSION_ID}_$(uname -m)/
export UV_CACHE_DIR=${UV_INSTALL_DIR}/cache
export UV_PYTHON_INSTALL_DIR=${UV_INSTALL_DIR}/python
export UV_LOCAL_CACHE_DIR=/opt/uv_local/cache/
export UV_LOCAL_PYTHON_INSTALL_DIR=${UV_LOCAL_CACHE_DIR}/python

# Create dirs (fix: multiple paths, no colon)
sudo mkdir -p "${UV_LOCAL_CACHE_DIR}" "${UV_CACHE_DIR}"
sudo mkdir -p "${UV_PYTHON_INSTALL_DIR}" "${UV_LOCAL_PYTHON_INSTALL_DIR}"

if [ "${ID}" = "ubuntu" ]; then
  sudo chown -R ubuntu:ubuntu "${UV_LOCAL_CACHE_DIR}" "${UV_INSTALL_DIR}"
else
  sudo chown -R opc:opc "${UV_LOCAL_CACHE_DIR}" "${UV_INSTALL_DIR}"
fi

############################
# Base OS packages (per distro)
############################
if [ "${ID}" = "ol" ] || [ "${ID}" = "centos" ]; then
  # Common tools needed later
  base_rpm_pkgs=(git ca-certificates curl jq)

  if [ "${vid}" = "7" ]; then
    # yum-config-manager requires yum-utils
    sudo yum install -y yum-utils || true
    sudo yum-config-manager --save --setopt=ol7_oci_included.skip_if_unavailable=true
    sudo yum makecache --enablerepo="${repo}"
    sudo yum install --enablerepo="${repo}" -y ansible python-netaddr python-dnf "${base_rpm_pkgs[@]}"
  elif [ "${vid}" = "8" ]; then
    sudo yum install -y yum-utils || true
    sudo yum makecache --enablerepo="${repo}"
    sudo yum install --enablerepo="${repo}" -y python38.x86_64 python38-dnf java-11-openjdk-headless http-parser "${base_rpm_pkgs[@]}"
    sudo python3.8 -m pip install --upgrade pip
  elif [ "${vid}" = "9" ]; then
    # dnf-plugins-core provides config-manager on newer distros
    sudo dnf install -y dnf-plugins-core || true
    sudo dnf install -y python3 python3-pip python3-dnf java-11-openjdk-headless http-parser "${base_rpm_pkgs[@]}"
    sudo python3 -m pip install --upgrade pip
  fi

elif [ "${ID}" = "debian" ] || [ "${ID}" = "ubuntu" ]; then
  # helper: wait if apt lock held
  fix_apt() {
    local apt_process
    apt_process=$(ps aux | grep "apt update" | grep -v grep | wc -l)
    apt_process=$(( apt_process - 1 ))
    while [ "${apt_process}" -ge 1 ]; do
      echo "wait until apt update is done"
      sleep 10s
      ps aux | grep "apt update" | grep -v grep || true
      apt_process=$(ps aux | grep "apt update" | grep -v grep | wc -l)
      apt_process=$(( apt_process - 1 ))
    done
  }
  fix_apt

  if [ "${ID}" = "debian" ] && [ "${VERSION_ID}" = "9" ]; then
    echo deb http://ppa.launchpad.net/ansible/ansible/ubuntu trusty main | sudo tee -a /etc/apt/sources.list
    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 93C4A3FD7BB9C367
  fi

  # disable unattended upgrades to reduce lock conflicts
  sudo sed -i 's/"1"/"0"/g' /etc/apt/apt.conf.d/20auto-upgrades || true
  sudo apt purge -y --auto-remove unattended-upgrades || true
  sudo systemctl stop apt-daily-upgrade.timer || true
  sudo systemctl disable apt-daily-upgrade.timer || true
  sudo systemctl mask apt-daily-upgrade.service || true
  sudo systemctl stop apt-daily.timer || true
  sudo systemctl disable apt-daily.timer || true
  sudo systemctl mask apt-daily.service || true

  sleep 10s

  sudo apt-mark hold linux-oracle linux-headers-oracle linux-image-oracle || true

  fix_apt
  sleep 10s
  sudo apt -y --fix-broken install || true

  fix_apt
  sudo apt update

  # Common tools (add gnupg & curl for repo keys and installers)
  common_apt_pkgs="python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9 git ca-certificates gnupg curl"

  if [ "${ID}" = "ubuntu" ] && [ "${VERSION_ID}" = "20.04" ]; then
    sudo apt-get -y install ${common_apt_pkgs}
  else
    # auto-restart services for noninteractive upgrades
    sudo sed -i "s/#\$nrconf{restart} = 'i';/\$nrconf{restart} = 'a';/" /etc/needrestart/needrestart.conf || true
    apt_success=1
    while [ "${apt_success}" -ge 1 ]; do
      echo "retry apt install common packages"
      sleep 10s
      sudo apt-get -y install ${common_apt_pkgs} || true
      apt_success=$?
      echo "apt rc=${apt_success}"
      [ "${apt_success}" -gt 0 ] || break
    done
  fi

  # second pass per-version (kept for parity)
  fix_apt
  sudo apt-get -y install ${common_apt_pkgs}

  # OCI CLI (latest)
  cd /tmp
  LATEST_OCICLI=$(curl -s -L https://api.github.com/repos/oracle/oci-cli/releases/latest | jq -r '.name')
  bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)" \
    -s --accept-all-defaults --install-dir /opt/oci-cli --oci-cli-version "$LATEST_OCICLI"  2>&1
fi

############################
# Install uv and Python toolchain
############################
curl -LsSf https://astral.sh/uv/install.sh > "${UV_INSTALL_DIR}/install.sh"
chmod +x "${UV_INSTALL_DIR}/install.sh"
"${UV_INSTALL_DIR}/install.sh"

# shellcheck disable=SC1090
source "${UV_INSTALL_DIR}/env"

if ( [ "${ID}" = "ol" ] || [ "${ID}" = "centos" ] ) && [ "${vid}" = "8" ]; then
  uv python install 3.10
else
  uv python install 3.12
fi

uv venv "${UV_INSTALL_DIR}/oci" --clear
# shellcheck disable=SC1090
source "${UV_INSTALL_DIR}/oci/bin/activate"

# Core Python deps
uv pip install -U pip
uv pip install ansible
if ( [ "${ID}" = "ol" ] || [ "${ID}" = "centos" ] ) && [ "${vid}" = "8" ]; then
  uv pip install "ansible-core==2.12"
fi

# OCI + runtime libraries
uv pip install oci-cli oci cryptography netaddr setuptools_rust requests urllib3 pyopenssl psutil distro
uv pip install prometheus_client watchdog opentelemetry-sdk opentelemetry-exporter-otlp
uv pip install pynvml pyudev clustershell sqlalchemy rich click ansible_runner pymysql memoization
uv pip install line-protocol-parser influx-line-protocol flatdict pssh parallel-ssh ldap3 orjson ujson
uv pip install "packaging>=24.1" "setuptools>=68" "wheel>=0.41" "build>=1.2.1"
uv pip install "typing_extensions>=4.12.2" "annotated_types>=0.6.0" "typing-inspect>=0.4.0" "pydantic>=2"
uv pip install "fastapi[standard-no-fastapi-cloud-cli]" uvicorn

export VENV_PATH="${UV_INSTALL_DIR}/oci"

# Ansible collections
"${VENV_PATH}/bin/ansible-galaxy" collection install ansible.netcommon --upgrade --force > /dev/null
"${VENV_PATH}/bin/ansible-galaxy" collection install community.general --upgrade --force > /dev/null
"${VENV_PATH}/bin/ansible-galaxy" collection install ansible.posix --force > /dev/null
"${VENV_PATH}/bin/ansible-galaxy" collection install community.crypto --force > /dev/null
"${VENV_PATH}/bin/ansible-galaxy" collection install ansible.utils --force > /dev/null

if ( [ "${ID}" = "ol" ] || [ "${ID}" = "centos" ] ) && [ "${vid}" = "8" ]; then
  export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
  export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt
  "${VENV_PATH}/bin/ansible-galaxy" collection install git+https://github.com/oracle/oci-ansible-collection.git > /dev/null
else
  "${VENV_PATH}/bin/ansible-galaxy" collection install oracle.oci --force > /dev/null
fi

# Ansible config
threads=$(nproc)
forks=$((threads * 8))

if [ ! -d /etc/ansible ] ; then
  sudo mkdir -p /etc/ansible
  if [ "${ID}" = "ubuntu" ]; then
    sudo chown ubuntu:ubuntu /etc/ansible
  else
    sudo chown opc:opc /etc/ansible
  fi
fi

"${VENV_PATH}/bin/ansible-config" init --disabled -t all | sudo tee /etc/ansible/ansible.cfg > /dev/null
sudo sed -i "s/^\(#\|;\)forks.*/forks = ${forks}/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)fact_caching=.*/fact_caching=jsonfile/" /etc/ansible/ansible.cfg
sudo sed -i "0,/^\(#\|;\)fact_caching_connection.*/s//fact_caching_connection=\/tmp\/ansible/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)bin_ansible_callbacks.*/bin_ansible_callbacks=True/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)stdout_callback.*/stdout_callback=yaml/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)retries.*/retries=5/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)connect_timeout.*/connect_timeout=300/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)command_timeout.*/command_timeout=120/" /etc/ansible/ansible.cfg

echo "Controller setup complete. VENV_PATH=${VENV_PATH}"