#!/bin/bash

cd /opt/oci-hpc/samples/nfs
sinfo -hNr -o "%N" > machinefile

sudo umount -l /nfs/scratch
PID=$!
wait $PID

pssh -i -h /opt/oci-hpc/samples/nfs/machinefile 'sudo umount -l /nfs/scratch'
PID=$!
wait $PID

sudo sed -i_bak -e "/ \/nfs\/scratch/d" /etc/fstab
PID=$!
wait $PID

pssh -i -h /opt/oci-hpc/samples/nfs/machinefile 'sudo sed -i_bak -e "/ \/nfs\/scratch/d" /etc/fstab'
PID=$!
wait $PID

ansible-playbook /opt/oci-hpc/playbooks/site.yml

