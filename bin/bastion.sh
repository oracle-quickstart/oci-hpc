#!/bin/bash
#
# Cluster init configuration script
#

#
# wait for cloud-init completion on the bastion host
#
execution=1

ssh_options="-i ~/.ssh/cluster.key -o StrictHostKeyChecking=no"
sudo cloud-init status --wait

source /etc/os-release

if [ $ID == "ol" ] ; then
  repo="ol7_developer_EPEL"
elif [ $ID == "centos" ] ; then 
  repo="epel"
fi

# to ensure existing enabled repos are available. 
if [ $ID == "ol" ] ; then 
  sudo osms unregister 
fi 

# Install ansible and other required packages

if [ $ID == "ol" ] || [ $ID == "centos" ] ; then 
  sudo yum makecache --enablerepo=$repo
  sudo yum install --enablerepo=$repo -y ansible python-netaddr
  sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
  sudo yum install -y terraform

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
  sudo systemctl disable apt-daily-upgrade.timer
  sudo systemctl mask apt-daily-upgrade.service
  sudo systemctl disable apt-daily.timer
  sudo systemctl mask apt-daily.service



  sleep 10s

  sudo apt-mark hold linux-oracle linux-headers-oracle linux-image-oracle

  fix_apt
  sleep 10s
  sudo apt -y --fix-broken install

  fix_apt

  sudo apt-get -y install ansible 
  output=$?
  if [ $output -ne 0 ]
  then
      fix_apt
      sudo apt-get -y install ansible 
  fi
  fix_apt
  sudo apt-get -y install python python-netaddr python3 python3-pip
  output=$?
  if [ $output -ne 0 ]
  then
      fix_apt
      sudo apt-get -y install python python-netaddr python3 python3-pip
  fi
  fix_apt

  pip install pip --upgrade
  pip install pyopenssl --upgrade

  # install oci-cli (add --oci-cli-version 3.23.3 or version that you know works if the latest does not work ) 
  bash -c "$(curl -L https://raw.githubusercontent.com/oracle/oci-cli/master/scripts/install/install.sh)" -s --accept-all-defaults

  # install oci module
  pip install oci

  wget -O- https://apt.releases.hashicorp.com/gpg | \
  gpg --dearmor | \
  sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg

  echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
    https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
    sudo tee /etc/apt/sources.list.d/hashicorp.list
  
  sudo apt update && sudo apt install terraform
  output=$?
  if [ $output -ne 0 ]
  then
      fix_apt  
      echo "Terraform second try"
      wget -O- https://apt.releases.hashicorp.com/gpg | \
      gpg --dearmor | \
      sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg

      echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
      https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
      sudo tee /etc/apt/sources.list.d/hashicorp.list
  
      sudo apt update && sudo apt install terraform
  fi
  fix_apt
fi 

ansible-galaxy collection install ansible.netcommon:=2.5.1 --force > /dev/null
ansible-galaxy collection install community.general:=4.8.1 --force > /dev/null
ansible-galaxy collection install ansible.posix > /dev/null

threads=$(nproc)
forks=$(($threads * 8))

sudo sed -i "s/^#forks.*/forks = ${forks}/" /etc/ansible/ansible.cfg
sudo sed -i "s/^#fact_caching=.*/fact_caching=jsonfile/" /etc/ansible/ansible.cfg
sudo sed -i "s/^#fact_caching_connection.*/fact_caching_connection=\/tmp\/ansible/" /etc/ansible/ansible.cfg
sudo sed -i "s/^#bin_ansible_callbacks.*/bin_ansible_callbacks=True/" /etc/ansible/ansible.cfg
sudo sed -i "s/^#stdout_callback.*/stdout_callback=yaml/" /etc/ansible/ansible.cfg
sudo sed -i "s/^#retries.*/retries=5/" /etc/ansible/ansible.cfg
sudo sed -i "s/^#connect_timeout.*/connect_timeout=300/" /etc/ansible/ansible.cfg
sudo sed -i "s/^#command_timeout.*/command_timeout=120/" /etc/ansible/ansible.cfg
