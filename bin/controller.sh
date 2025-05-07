#!/bin/bash
#
# Cluster init configuration script
#

#
# wait for cloud-init completion on the controller host
#
execution=1

ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
sudo cloud-init status --wait

source /etc/os-release

vid=`echo $VERSION|awk -F. '{print $1}'`
if [ $ID == "ol" ] ; then
  if [ $vid == 7 ] ; then
    repo="ol7_developer_EPEL"
  elif [ $vid == 8 ] ; then
    repo="ol8_developer_EPEL"
  elif [ $vid == 9 ] ; then
    repo="ol9_developer_EPEL"
  fi
elif [ $ID == "centos" ] ; then
  repo="epel"
fi

# to ensure existing enabled repos are available. 
if [ $ID == "ol" ] ; then 
  sudo osms unregister 
fi 

# Install ansible and other required packages

if [ $ID == "ol" ] || [ $ID == "centos" ] ; then 
  if [ $vid == 7 ]; then
    sudo yum-config-manager --save --setopt=ol7_oci_included.skip_if_unavailable=true
    sudo yum makecache --enablerepo=$repo
    sudo yum install --enablerepo=$repo -y ansible python-netaddr
    sudo python3 -m pip install virtualenv
    virtualenv /config/venv --always-copy
    source /config/venv/bin/activate
  elif [ $vid == 8 ] ; then
    sudo yum makecache --enablerepo=$repo
    sudo yum install --enablerepo=$repo -y python38.x86_64
    sudo python3.8 -m pip install --upgrade pip
    sudo python3.8 -m pip install virtualenv
    virtualenv /config/venv --always-copy
    source /config/venv/bin/activate
    /config/venv/bin/python3 -m pip install ansible cryptography netaddr > /dev/null
    sudo mkdir /etc/ansible
    sudo ln -s /usr/local/bin/ansible-playbook /bin/ansible-playbook
    sudo ln -s /usr/local/bin/ansible /bin/ansible
  elif [ $vid == 9 ] ; then
    sudo dnf install python3 python3-pip
    sudo python3 -m pip install --upgrade pip
    sudo python3 -m pip install virtualenv
    virtualenv /config/venv
    source /config/venv/bin/activate
    /config/venv/bin/python3 -m pip install ansible cryptography netaddr > /dev/null
    sudo mkdir /etc/ansible
    sudo ln -s /usr/local/bin/ansible-playbook /bin/ansible-playbook
    sudo ln -s /usr/local/bin/ansible /bin/ansible
  fi
  sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
  sudo sed -i 's/$releasever/'"${vid}"'/g' /etc/yum.repos.d/hashicorp.repo
  sudo yum install -y terraform
  /config/venv/bin/python3 -m pip install netaddr --upgrade > /dev/null
  /config/venv/bin/python3 -m pip install setuptools_rust --upgrade > /dev/null
  /config/venv/bin/python3 -m pip install requests --upgrade > /dev/null
  /config/venv/bin/python3 -m pip install urllib3 --upgrade > /dev/null
  /config/venv/bin/python3 -m pip install oci-cli --upgrade > /dev/null


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
  echo Before
  if [ $ID == "ubuntu" ] && [ $VERSION_ID == "20.04" ] ; then
    sudo apt-get -y install python python-netaddr python3 python3-pip
  else
    sudo sed -i 's/#$nrconf{restart} = '"'"'i'"'"';/$nrconf{restart} = '"'"'a'"'"';/g' /etc/needrestart/needrestart.conf
    apt_success=1
    while [ $apt_success -ge 1 ]
      do
        echo "wait until apt update is done"
        sleep 10s
        sudo apt-get -y install python3 python3-netaddr python3-pip
        apt_success=$?
        echo $apt_success
      done
    sudo ln -s /usr/bin/python3 /usr/bin/python
  fi

  echo ${VERSION_ID}
  if [ $ID == "ubuntu" ] && [ $VERSION_ID == "20.04" ] ; then
    fix_apt
    sudo apt-get -y install python python-netaddr python3 python3-pip
    sudo python3 -m pip install virtualenv
  elif [ $ID == "ubuntu" ] && [ $VERSION_ID == "22.04" ] ; then
    fix_apt
    sudo apt-get -y install python3 python3-netaddr python3-pip
    sudo python3 -m pip install virtualenv
  else
    fix_apt
    sudo apt-get -y install python3 python3-netaddr python3-pip
    fix_apt
    sudo apt-get -y install python3-virtualenv
  fi
  virtualenv /config/venv 
  source /config/venv/bin/activate
  /config/venv/bin/python3 -m pip install ansible
  /config/venv/bin/python3 -m pip install -U pip > /dev/null
  /config/venv/bin/python3 -m pip install netaddr --upgrade > /dev/null
  /config/venv/bin/python3 -m pip install requests --upgrade > /dev/null
  /config/venv/bin/python3 -m pip install urllib3 --upgrade > /dev/null
  /config/venv/bin/pip install pip --upgrade > /dev/null
  /config/venv/bin/pip install pyopenssl --upgrade > /dev/null

  # install oci-cli (add --oci-cli-version 3.23.3 or version that you know works if the latest does not work ) 
  cd /tmp
  bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)" -s --accept-all-defaults > /dev/null

  # install oci module
  /config/venv/bin/pip install oci > /dev/null
fi 

ansible-galaxy collection install ansible.netcommon:=2.5.1 --force > /dev/null
ansible-galaxy collection install community.general:=4.8.1 --force > /dev/null
ansible-galaxy collection install ansible.posix --force > /dev/null
ansible-galaxy collection install community.crypto --force > /dev/null

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

ansible-config init --disabled -t all | sudo tee /etc/ansible/ansible.cfg > /dev/null
sudo sed -i "s/^\(#\|;\)forks.*/forks = ${forks}/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)fact_caching=.*/fact_caching=jsonfile/" /etc/ansible/ansible.cfg
sudo sed -i "0,/^\(#\|;\)fact_caching_connection.*/s//fact_caching_connection=\/tmp\/ansible/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)bin_ansible_callbacks.*/bin_ansible_callbacks=True/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)stdout_callback.*/stdout_callback=yaml/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)retries.*/retries=5/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)connect_timeout.*/connect_timeout=300/" /etc/ansible/ansible.cfg
sudo sed -i "s/^\(#\|;\)command_timeout.*/command_timeout=120/" /etc/ansible/ansible.cfg

