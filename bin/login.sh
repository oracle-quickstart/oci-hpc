#!/bin/bash
#
# Cluster init configuration script
#

#
# wait for cloud-init completion on the controller host
#
echo login.sh
if [ $# -eq 0 ] 
then
  cluster_name=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.cluster_name`
else
  cluster_name=$1
fi

echo "ClusterName:" $cluster_name
ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"

source /etc/os-release
if [ ! -d /opt/oci-hpc ] ; then
  sudo mkdir /opt/oci-hpc
fi   
if [ $ID == "ubuntu" ] ; then
  sudo chown -R ubuntu:ubuntu /opt/
else
  sudo chown -R opc:opc /opt/
fi

vid=`echo $VERSION|awk -F. '{print $1}'`
if [ $ID == "ol" ] ; then
  if [ $vid == 7 ] ; then
    repo="ol7_developer_EPEL"
    sudo osms unregister 
  elif [ $vid == 8 ] ; then
    repo="ol8_developer_EPEL"
    sudo osms unregister 
  elif [ $vid == 9 ] ; then
    repo="ol9_developer_EPEL"
  fi
elif [ $ID == "centos" ] ; then
  repo="epel"
fi

export UV_INSTALL_DIR=/config/venv/${ID^}_${VERSION_ID}_$(uname -m)/
export VENV_PATH=${UV_INSTALL_DIR}/oci
if [ ! -d "${UV_INSTALL_DIR}" ]; then
  export creating_python_install_dir=true
  export UV_CACHE_DIR=${UV_INSTALL_DIR}/cache
  export UV_PYTHON_INSTALL_DIR=${UV_INSTALL_DIR}/python
  export UV_LOCAL_CACHE_DIR=/opt/uv_local/cache/
  export UV_LOCAL_PYTHON_INSTALL_DIR=${UV_LOCAL_CACHE_DIR}/python

  sudo mkdir -p ${UV_LOCAL_CACHE_DIR}
  sudo mkdir -p ${UV_CACHE_DIR}:${UV_LOCAL_CACHE_DIR}
  sudo mkdir -p ${UV_PYTHON_INSTALL_DIR}:${UV_LOCAL_PYTHON_INSTALL_DIR}
  if [ $ID == "ubuntu" ] ; then
    sudo chown -R ubuntu:ubuntu ${UV_LOCAL_CACHE_DIR}
    sudo chown -R ubuntu:ubuntu ${UV_INSTALL_DIR}
  else
    sudo chown -R opc:opc ${UV_LOCAL_CACHE_DIR}
    sudo chown -R opc:opc ${UV_INSTALL_DIR}
  fi
fi

# Install ansible and other required packages
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then 
  if [ $vid == 7 ]; then
    sudo yum-config-manager --save --setopt=ol7_oci_included.skip_if_unavailable=true
    sudo yum makecache --enablerepo=$repo
    sudo yum install --enablerepo=$repo -y ansible python-netaddr python-dnf
  elif [ $vid == 8 ] ; then
    sudo yum makecache --enablerepo=$repo
    sudo yum install --enablerepo=$repo -y python38.x86_64 python38-dnf java-11-openjdk-headless http-parser
    sudo python3.8 -m pip install --upgrade pip
  elif [ $vid == 9 ] ; then
    sudo dnf install -y python3 python3-pip python3-dnf java-11-openjdk-headless http-parser
    sudo python3 -m pip install --upgrade pip
  fi

elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then 
  # checking here as well to be sure that the lock file is not being held
  function fix_apt {
    apt_process=`ps aux | grep "apt update" | grep -v grep | wc -l`
    apt_process=$(( apt_process -1 ))
    while [ $apt_process -ge 1 ]
      do
        echo "wait until apt update is done"
        sleep 10s
        ps aux | grep "apt update" | grep -v grep
        apt_process=`ps aux | grep "apt update" | grep -v grep | wc -l`
        apt_process=$(( apt_process -1 ))
      done
  }
  fix_apt

  if [ $ID == "debian" ] && [ $VERSION_ID == "9" ] ; then 
    echo deb http://ppa.launchpad.net/ansible/ansible/ubuntu trusty main | sudo tee -a /etc/apt/sources.list
    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 93C4A3FD7BB9C367
  fi 

  sudo sed -i 's/"1"/"0"/g' /etc/apt/apt.conf.d/20auto-upgrades
  sudo apt purge -y --auto-remove unattended-upgrades
  sudo systemctl stop apt-daily-upgrade.timer
  sudo systemctl disable apt-daily-upgrade.timer
  sudo systemctl mask apt-daily-upgrade.service
  sudo systemctl stop apt-daily.timer
  sudo systemctl disable apt-daily.timer
  sudo systemctl mask apt-daily.service

  sleep 10s

  sudo apt-mark hold linux-oracle linux-headers-oracle linux-image-oracle

  fix_apt
  sleep 10s
  sudo apt -y --fix-broken install

  fix_apt
  sudo apt update
  if [ $ID == "ubuntu" ] && [ $VERSION_ID == "20.04" ] ; then
    sudo apt-get -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  else
    sudo sed -i 's/#$nrconf{restart} = '"'"'i'"'"';/$nrconf{restart} = '"'"'a'"'"';/g' /etc/needrestart/needrestart.conf
    apt_success=1
    while [ $apt_success -ge 1 ]
      do
        echo "wait until apt update is done"
        sleep 10s
        sudo apt-get -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
        apt_success=$?
        echo $apt_success
      done
  fi
  if [ $ID == "ubuntu" ] && [ $VERSION_ID == "20.04" ] ; then
    fix_apt
    sudo apt-get -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  elif [ $ID == "ubuntu" ] && [ $VERSION_ID == "22.04" ] ; then
    fix_apt
    sudo apt-get -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  else
    fix_apt
    sudo apt-get -y install python3 python3-pip jq openjdk-11-jre-headless libhttp-parser2.9
  fi
  # install oci-cli (add --oci-cli-version 3.23.3 or version that you know works if the latest does not work ) 
  cd /tmp
  LATEST_OCICLI=$(curl -s -L https://api.github.com/repos/oracle/oci-cli/releases/latest | jq -r '.name')

  # First try to install into /opt/oci-cli
   bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)" \
      -s --accept-all-defaults --install-dir /opt/oci-cli --oci-cli-version "$LATEST_OCICLI"  2>&1
fi


# install uv  
if [ $creating_python_install_dir ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh

  source ${UV_INSTALL_DIR}/env

  if ( [ $ID == "ol" ] || [ $ID == "centos" ] ) && [ $vid == 8 ] ; then 
      uv python install 3.10 --force
  else
      uv python install 3.12 --force
  fi
  uv venv ${UV_INSTALL_DIR}/oci --clear
  source ${UV_INSTALL_DIR}/oci/bin/activate
  uv pip install pip
  uv pip install ansible
  if [ $ID == "ol" ] || [ $ID == "centos" ] ; then 
    if [ $vid == 8 ]; then
      uv pip install ansible-core==2.12.9
    fi
  fi
  uv pip install oci-cli
  uv pip install oci
  uv pip install cryptography
  uv pip install netaddr
  uv pip install setuptools_rust
  uv pip install requests
  uv pip install urllib3
  uv pip install pyopenssl
  uv pip install psutil
  uv pip install distro
  uv pip install prometheus_client
  uv pip install watchdog
  uv pip install opentelemetry-sdk
  uv pip install opentelemetry-exporter-otlp
  uv pip install pynvml
  uv pip install pyudev
  uv pip install clustershell
  uv pip install sqlalchemy
  uv pip install rich
  uv pip install click
  uv pip install ansible_runner
  uv pip install pymysql
  uv pip install cachetools
  uv pip install line-protocol-parser
  uv pip install influx-line-protocol
  uv pip install flatdict
  uv pip install pssh
  uv pip install parallel-ssh
  uv pip install ldap3
  uv pip install orjson

  # --- Python build toolchain packages for Slurm SDK ---
  echo "Installing Python build toolchain and SDK dependencies..."
  uv pip install "packaging>=24.1"
  uv pip install "setuptools>=68"
  uv pip install "wheel>=0.41"
  uv pip install "build>=1.2.1"

  # --- Slurm SDK runtime dependencies ---
  echo "Installing Slurm SDK runtime dependencies..."
  uv pip install "typing_extensions>=4.12.2"
  uv pip install "annotated_types>=0.6.0"
  uv pip install "typing-inspect>=0.4.0"
  uv pip install "pydantic>=2"

  # Other packages
  uv pip install ujson
  uv pip install "fastapi[standard-no-fastapi-cloud-cli]"
  uv pip install uvicorn

  $VENV_PATH/bin/ansible-galaxy collection install ansible.netcommon --upgrade --force > /dev/null
  $VENV_PATH/bin/ansible-galaxy collection install ansible.posix --upgrade --force > /dev/null
  $VENV_PATH/bin/ansible-galaxy collection install community.crypto --upgrade --force > /dev/null
  $VENV_PATH/bin/ansible-galaxy collection install ansible.utils --upgrade --force > /dev/null
  $VENV_PATH/bin/ansible-galaxy collection install community.general --upgrade --force > /dev/null
  if ( [ $ID == "ol" ] || [ $ID == "centos" ] ) && [ $vid == 8 ] ; then 
      export REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
      export SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt
      # $VENV_PATH/bin/ansible-galaxy collection install community.general==9.5.2 --upgrade --force > /dev/null
      $VENV_PATH/bin/ansible-galaxy collection install git+https://github.com/oracle/oci-ansible-collection.git > /dev/null
  else
      $VENV_PATH/bin/ansible-galaxy collection install oracle.oci --upgrade --force > /dev/null
  fi
fi

threads=$(nproc)
forks=$(($threads * 8))

if [ ! -d /etc/ansible ] ; then
  sudo mkdir /etc/ansible
  if [ $ID == "ubuntu" ] ; then
    sudo chown ubuntu:ubuntu /etc/ansible
  else
    sudo chown opc:opc /etc/ansible
  fi
fi

$VENV_PATH/bin/ansible-config init --disabled -t all | sudo tee /etc/ansible/ansible.cfg > /dev/null
sudo sed -i "s/^\(#\|;\)forks.*/forks = ${forks}/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)fact_caching=.*/fact_caching=jsonfile/" /etc/ansible/ansible.cfg
sudo sed -i "0,/^\(#\|;\)fact_caching_connection.*/s//fact_caching_connection=\/tmp\/ansible/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)bin_ansible_callbacks.*/bin_ansible_callbacks=True/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)retries.*/retries=5/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)connect_timeout.*/connect_timeout=300/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)command_timeout.*/command_timeout=120/" /etc/ansible/ansible.cfg
sudo sed -i "/^\[defaults\]/,/^\[/ s/^\(#\|;\)remote_tmp.*/remote_tmp=\/tmp\/.ansible-tmp/" /etc/ansible/ansible.cfg

# Ensure the remote temp directory exists and is usable for any user (including become: true tasks)
sudo mkdir -p /tmp/.ansible-tmp
sudo chmod 1777 /tmp/.ansible-tmp

# Replace the legacy yaml callback with the built-in default and enable YAML output
sudo sed -i 's/^\([#;]\s*\)\?stdout_callback.*/stdout_callback = default/' /etc/ansible/ansible.cfg
# Ensure the default callback outputs YAML (append the section if not present)
if ! sudo grep -q '^\[callback_default\]' /etc/ansible/ansible.cfg; then
  sudo tee -a /etc/ansible/ansible.cfg >/dev/null <<'EOF'
[callback_default]
result_format = yaml
EOF
else
  # Make sure result_format=yaml is set under [callback_default]
  sudo sed -i '/^\[callback_default\]/,/^\[/{s/^\([#;]\s*\)\?result_format.*/result_format = yaml/}' /etc/ansible/ansible.cfg
fi
modified_hostname=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .displayName`
echo $modified_hostname
log=/config/logs/${modified_hostname}.log
max_attempts=5
max_attempts_ansible_install=50
attempt=1

while [ $attempt -le $max_attempts_ansible_install ]; do
    echo "Attempt $attempt of $max_attempts_ansible_install: Is ansible installed?" | tee -a $log
    $VENV_PATH/bin/ansible localhost -c local -m ping 2>&1 | tee -a $log
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "Ansible is installed!" | tee -a $log
        break
    else
        echo "Ansible is not installed. " | tee -a $log
        if [ $attempt -lt $max_attempts_ansible_install ]; then
            echo "Retrying..." | tee -a $log
            sleep 30s
        else
            echo "Max attempts ($max_attempts_ansible_install) reached. Giving up." | tee -a $log
        fi
        ((attempt++))
    fi
done 

attempt=1
wait_time=1
while [ $attempt -le $max_attempts ]; do
    echo "Attempt $attempt of $max_attempts: Configuring the node" | tee -a $log
    $VENV_PATH/bin/ansible-playbook -i /config/playbooks/inventory /config/playbooks/login.yml 2>&1 | tee -a $log
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "Ansible succeeded!" | tee -a $log
        break
    else
        echo "Ansible failed. " | tee -a $log
        if [ $attempt -lt $max_attempts ]; then
            echo "Retrying in ($wait_time)s ..." | tee -a $log
            sleep $wait_time
            wait_time=$((wait_time * 2))
        else
            echo "Max attempts ($max_attempts) reached. Giving up." | tee -a $log
        fi
        ((attempt++))
    fi
done 
