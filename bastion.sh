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
  if [ $ID == "debian" ] && [ $VERSION_ID == "9" ] ; then 
    echo deb http://ppa.launchpad.net/ansible/ansible/ubuntu trusty main | sudo tee -a /etc/apt/sources.list
    sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 93C4A3FD7BB9C367
  fi 
  sudo apt-get update
  sudo apt -y install ansible python-netaddr

fi 

ansible-galaxy collection install ansible.netcommon > /dev/null
ansible-galaxy collection install community.general > /dev/null
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
