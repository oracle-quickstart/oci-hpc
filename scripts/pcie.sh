#!/bin/bash

source /etc/os-release
if [ $ID == "ol" ] || [ $ID == "centos" ] ; then
  for dev in `/usr/sbin/lspci | grep ConnectX-5 | awk '{print $1}'`
  do
    echo ${dev}
    sudo lspci -vvv -s ${dev} | grep LnkSta:
  done
elif [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then
  for dev in `/usr/bin/lspci | grep ConnectX-5 | awk '{print $1}'`
  do
    echo ${dev}
    sudo lspci -vvv -s ${dev} | grep LnkSta:
  done
fi

