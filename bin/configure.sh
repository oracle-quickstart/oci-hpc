#!/bin/bash
#
# Cluster init configuration script
#

#
# wait for cloud-init completion on the controller host
#
execution=1

if [ -n "$1" ]; then
  playbook=$1
else
  playbook="/config/playbooks/site.yml"
fi

if [ -n "$2" ]; then
  inventory=$2
else
  inventory="/etc/ansible/hosts"
fi

username=`cat $inventory | grep compute_username= | tail -n 1| awk -F "=" '{print $2}'`
clustername=`cat $inventory | grep compute_username= | tail -n 1| awk -F "=" '{print $2}'`
if [ "$username" == "" ]
then
username=$USER
fi


source /etc/os-release
VENV_OS_ARCH="${ID^}_${VERSION_ID}_$(uname -m)"

if [ -f /config/playbooks/inventory ] ; then 
  sed -i "s|##VENV_OS_ARCH##|$VENV_OS_ARCH|g" /config/playbooks/inventory
  sudo cp /config/playbooks/inventory /etc/ansible/hosts
  sudo chown $username:$username /etc/ansible/hosts
  clustername=`cat /etc/ansible/hosts | grep cluster_name= | tail -n 1| awk -F "=" '{print $2}'`
  sudo cp /config/playbooks/inventory /config/playbooks/inventory_${clustername}
  sudo chown $username:$username /config/playbooks/inventory_${clustername}
fi 

# Update the forks to a 8 * threads


#
# Ansible will take care of key exchange and learning the host fingerprints, but for the first time we need
# to disable host key checking.
#
export UV_INSTALL_DIR=/config/venv/${ID^}_${VERSION_ID}_$(uname -m)/
export VENV_PATH=${UV_INSTALL_DIR}/oci

# Always use the system-wide ansible.cfg we generated in controller.sh
export ANSIBLE_CONFIG=/etc/ansible/ansible.cfg

if [[ $execution -eq 1 ]] ; then
  ANSIBLE_HOST_KEY_CHECKING=False $VENV_PATH/bin/ansible --private-key ~/.ssh/cluster.key all -m setup --tree /tmp/ansible > /dev/null 2>&1
  ANSIBLE_HOST_KEY_CHECKING=False $VENV_PATH/bin/ansible-playbook --private-key ~/.ssh/cluster.key $playbook -i $inventory
else

        cat <<- EOF > /tmp/motd
        At least one of the cluster nodes has been innacessible during installation. Please validate the hosts and re-run:
        ANSIBLE_HOST_KEY_CHECKING=False $VENV_PATH/bin/ansible-playbook --private-key ~/.ssh/cluster.key /config/playbooks/site.yml
EOF

sudo mv /tmp/motd /etc/motd

fi