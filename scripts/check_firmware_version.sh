#!/bin/bash
# check_firmware_version.sh

# Script to check the firmware version on the nodes. 
# Needs one argument which is a hostfile (one host per line). 
# Example: ./check_firmware_version.sh hosts

# check if host file is passed
if [ -n "$1" ]; then
  HOST_FILE=$1
else
  echo "scriptname <path-to-host-file>"
  echo "host file is missing, pass a file with list of hostname, one host per line"
  exit 1;
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

for h in `less $HOST_FILE` ;
  do
    echo $h
    ssh $USERNAME@$h "/usr/sbin/ibstat | grep 'Firmware version'"
  done