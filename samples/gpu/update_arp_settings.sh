#!/bin/bash

# arp change for single subnet for all RoCE NICs only.
links=$(/sbin/ip link | grep -e "enp.*s0f*" | grep -v enp45 | awk -F":" "{print \$2}")
parameters="rp_filter=2 arp_ignore=2 arp_announce=1"

for link in ${links}
do
  for param in ${parameters}
    do
        echo "${link} current: " $(sudo sysctl net.ipv4.conf.${link}.${param})
        sudo sysctl -w net.ipv4.conf.${link}.${param}
    done
done


# Permanent/Persistent change
# arp change for single subnet for all RoCE NICs only.
links=$(/sbin/ip link | grep -e "enp.*s0f*" | grep -v enp45 | awk -F":" "{print \$2}")
parameters="rp_filter=2 arp_ignore=2 arp_announce=1"

sysctl_network_conf="/etc/sysctl.d/80-network.conf"
less $sysctl_network_conf | grep "rp_filter=2"
if [ $? -ne 0 ]; then
  for link in ${links}
    do
        for param in ${parameters}
            do
                echo "net.ipv4.conf.${link}.${param}"  | sudo tee -a  $sysctl_network_conf
            done
    done
fi

