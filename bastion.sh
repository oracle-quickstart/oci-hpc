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

# TODO: investigate repository issues. 
sleep 30

source /etc/os-release

if [ $ID == "ol" ] ; then
  repo="ol7_developer_EPEL"
else
  repo="epel"
fi


# Install ansible and other required packages

sudo yum makecache --enablerepo=$repo
sudo yum install --enablerepo=$repo -y ansible python-netaddr
sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
sudo yum install -y terraform
#sudo yum makecache
#sudo yum install -y ansible python-netaddr

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
