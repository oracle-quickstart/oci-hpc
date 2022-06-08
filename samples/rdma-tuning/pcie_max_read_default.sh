#!/bin/bash
#
# https://support.mellanox.com/s/article/understanding-pcie-configuration-for-maximum-performance
#

PCI_DEVICES_48=""
shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.B4.8\" ]
then
  PCI_DEVICES_48="0c:00.0 0c:00.1 16:00.0 16:00.1 47:00.0 47:00.1 4b:00.0 4b:00.1 89:00.0 89:00.1 93:00.0 93:00.1 c3:00.0 c3:00.1 d1:00.0 d1:00.1"
elif [ $shape == \"BM.GPU4.8\" ]
then
  PCI_DEVICES_48="0c:00.0 0c:00.1 16:00.0 16:00.1 48:00.0 48:00.1 4c:00.0 4c:00.1 8a:00.0 8a:00.1 94:00.0 94:00.1 c3:00.0 c3:00.1 d1:00.0 d1:00.1"
fi

#
for d in ${PCI_DEVICES_48}
do
  echo ${d}
  sudo lspci -s ${d} -vvv | grep MaxRead
  sudo setpci -s ${d} 68.w
  # 2937 is the default
  # 2 is 512B
  # 5 is 4096B
  OUT=`sudo setpci -s ${d} 68.w | cut -c2-5`
  echo sudo setpci -s ${d} 68.w=2${OUT}
  sudo setpci -s ${d} 68.w=2${OUT}
  sudo lspci -s ${d} -vvv | grep MaxRead
  sudo setpci -s ${d} 68.w
  echo
done