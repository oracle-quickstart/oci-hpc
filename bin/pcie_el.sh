#!/bin/bash
 
for dev in `/usr/sbin/lspci | grep ConnectX-5 | awk '{print $1}'`
do
  echo ${dev}
  sudo lspci -vvv -s ${dev} | grep LnkSta:
done

