#!/bin/bash

sed -i  's|NETMASK=255.255.252.0|NETMASK=255.255.0.0|g'  /etc/sysconfig/network-scripts/ifcfg-enp*

