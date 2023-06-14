#!/bin/bash
# mlx_firmware_update.sh

# This script updates the roce_tx_window_en setting and oci-cn-auth package. 
# It needs mandatory one argument which is a hostfile (one host per line). 
# After updating, it also returns the roce_tx_window_en setting and oci-cn-auth version.
# If you specify the optional 2nd argument "check", then it will not update but only return the current roce_tx_window_en setting 
# and oci-cn-auth version.
# Example:
# ./mlx_firmware_update.sh hosts
# ./mlx_firmware_update.sh hosts check

MODE=update

# check if host file is passed
if [ -n "$1" ]; then
  HOST_FILE=$1
else
  echo "scriptname <path-to-host-file>"
  echo "host file is missing, pass a file with list of hostname, one host per line"
  exit 1;
fi

# optional parameter to check the changes
if [ -n "$2" ]; then
  if [ "$2" == "check" ]; then
      	MODE="check"
  fi
fi



# check if ubuntu or oracle
source /etc/os-release

if [ $ID == "ol" ] ; then
  echo "oracle"
  USERNAME=opc
fi

if [ $ID == "ubuntu" ] ; then
  echo "ubuntu"
  USERNAME=ubuntu
fi


function check_roce_tx_window_en {
    cat > ./check_roce_tx_window_en.sh  << EOF
#!/bin/bash
# check roce_tx_window_en setting
#
#
mlxreg=\$(which mlxreg)
shape=\$(curl -q -s 169.254.169.254/opc/v1/instance/shape)
for pci_id in \$(cat /opt/oci-hpc/oci-cn-auth/configs/shapes.json | jq '.["hpc-shapes"]' | jq ".[] | select(.shape==\"\$shape\") " | jq -r '.["rdma-nics"] | .[].pci') ; do
echo \$pci_id ; \$mlxreg --yes -d \$pci_id --reg_name ROCE_ACCL --get | grep roce_tx_window_en
done

EOF

chmod +x ./check_roce_tx_window_en.sh

for h in `less $HOST_FILE` ;
  do
    echo $h
    scp ./check_roce_tx_window_en.sh  $USERNAME@$h:/tmp/
  done


for h in `less $HOST_FILE` ;
  do
    echo $h
    ssh $USERNAME@$h "sudo /tmp/check_roce_tx_window_en.sh"
  done
  }

function check_oci_cn_auth_version {
  for h in `less $HOST_FILE` ;
  do
    echo $h
    ssh $USERNAME@$h "cat /opt/oci-hpc/oci-cn-auth/.version-oci_cn_auth"
  done
}

if [ $MODE == "check" ] ; then
  check_roce_tx_window_en
  check_oci_cn_auth_version

else


# generate ./update_roce_tx_window_en.sh file
cat > ./update_roce_tx_window_en.sh  << EOF
#!/bin/bash
# Script to set roce_tx_window_en=0
#
#
mlxreg=\$(which mlxreg)
shape=\$(curl -q -s 169.254.169.254/opc/v1/instance/shape)
for pci_id in \$(cat /opt/oci-hpc/oci-cn-auth/configs/shapes.json | jq '.["hpc-shapes"]' | jq ".[] | select(.shape==\"\$shape\") " | jq -r '.["rdma-nics"] | .[].pci') ; do
echo \$pci_id ; \$mlxreg --yes -d \$pci_id --reg_name ROCE_ACCL --set roce_tx_window_en=0
done

EOF

chmod +x ./update_roce_tx_window_en.sh

# generate install file
cat > ./install_oci-cn-auth-package.sh  << EOF
#!/bin/bash

#DEBIAN_FRONTEND=noninteractive

# check if ubuntu or oracle
source /etc/os-release

# download file
UBUNTU_PACKAGE_URL="https://objectstorage.eu-frankfurt-1.oraclecloud.com/p/F7gihhVuJbrnsV8KjAMA7XblkZYRBYJ2xAH2FPmaIJrgtYcuy5wJRWAQXMfw9hLD/n/hpc/b/source/o/oci-cn-auth_2.1.4-compute_all.deb"
UBUNTU_PACKAGE="/tmp/oci-cn-auth_2.1.4-compute_all.deb"
ORACLE_PACKAGE_URL="https://objectstorage.eu-frankfurt-1.oraclecloud.com/p/F7gihhVuJbrnsV8KjAMA7XblkZYRBYJ2xAH2FPmaIJrgtYcuy5wJRWAQXMfw9hLD/n/hpc/b/source/o/oci-cn-auth-2.1.4-compute.el7.noarch.rpm"
ORACLE_PACKAGE="/tmp/oci-cn-auth-2.1.4-compute.el7.noarch.rpm"


if [ \$ID == "ol" ] ; then
  echo "oracle"
  USERNAME=opc
  wget -O \$ORACLE_PACKAGE  \$ORACLE_PACKAGE_URL
  sudo yum localinstall -y -q  \$ORACLE_PACKAGE
fi

if [ \$ID == "ubuntu" ] ; then
  echo "ubuntu"
  USERNAME=ubuntu
  wget -O \$UBUNTU_PACKAGE  \$UBUNTU_PACKAGE_URL
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q  \$UBUNTU_PACKAGE
fi


EOF

chmod +x ./install_oci-cn-auth-package.sh


# Run for loop to copy file to all nodes and execute them
for h in `less $HOST_FILE` ;
  do
    echo $h
    scp ./install_oci-cn-auth-package.sh  $USERNAME@$h:/tmp/
    scp ./update_roce_tx_window_en.sh  $USERNAME@$h:/tmp/
  done

#exit 0

for h in `less $HOST_FILE` ;
  do
    echo $h
    ssh $USERNAME@$h "sudo /tmp/update_roce_tx_window_en.sh"
    ssh $USERNAME@$h "sudo /tmp/install_oci-cn-auth-package.sh"
  done

check_roce_tx_window_en
check_oci_cn_auth_version

fi
