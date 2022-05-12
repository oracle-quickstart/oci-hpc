#!/usr/bin/env python3
from pssh.clients import ParallelSSHClient
import json
import sys, getopt
import os
import argparse
from operator import itemgetter
from collections import OrderedDict

def write_ordered_hostfile(ordered_hosts=[],hostfile=None):
   #ordered_hostfile="ordered_hostfile"
   if os.path.isfile(hostfile):
      os.remove(hostfile)
   fhandler = open(hostfile,"w")
   for h in ordered_hosts:
      fhandler.write(h+"\n")
   fhandler.close()

def write_ordered_rankfile(ordered_hosts=[],hostfile=None):
    if os.path.isfile(hostfile):
       os.remove(hostfile)
    fhandler = open(hostfile,"w")
    for index,h in enumerate(ordered_hosts):
        for gpu_index in range(gpus):
            fhandler.write("rank "+str(index*gpus+gpu_index)+"="+h+" slot="+str(gpu_index)+"\n")
    fhandler.close()


gpus=8
parser = argparse.ArgumentParser(description='Script to order hostnames for optimal performance based on rack Id')
parser.add_argument('--input_file', help='Path of the input file which has host names. One hostname on each line in the file')
args = parser.parse_args()

if args.input_file is None:
    input_file=''
    #/etc/opt/oci-hpc/hostfile.tcp'
    exit()
else:
    input_file=args.input_file

with open(input_file, 'r') as f:
#with open('./hostfile', 'r') as f:
#with open('/etc/opt/oci-hpc/hostfile.tcp', 'r') as f:
  hosts = f.read().splitlines()

client = ParallelSSHClient(hosts)
output = client.run_command('curl http://169.254.169.254/opc/v1/host/')
#print(output)

r = {}
for host_out in output:
    j = json.loads(bytearray(''.join(list(host_out.stdout)).encode()))
    #print(j)
    if j['rackId'] in r:
       r[j['rackId']].append( host_out.host )
    else:
       r[j['rackId']] = [ host_out.host ]


friendly_name_to_system_hostname = {}
hostname_output = client.run_command('/usr/bin/hostname')
#print(hostname_output)
for host_out in hostname_output:
    #j = bytearray(''.join(list(host_out.stdout)).encode())
    j = bytearray(''.join(list(host_out.stdout)).encode())
    friendly_name_to_system_hostname[host_out.host] = j.decode(encoding='ascii')
    #print(j.decode(encoding='ascii')+"   "+host_out.host)


ordered_hosts = []
ordered_hosts_friendly_name = []
# sort racks by amount of hosts (descending)
racks_sorted = sorted(r.items(), key=lambda x: len(x[1]), reverse=True)
i = 0
for k, v in racks_sorted:
  i += 1
  print(f'# rack {i}')
  rack_data_prefix = "SwitchName=rack"+str(i)+" Nodes="
  rack_nodes = []
  for h in v:
    print(h)
    ordered_hosts.append(h)
    ordered_hosts_friendly_name.append(friendly_name_to_system_hostname[h])
    rack_nodes.append(friendly_name_to_system_hostname[h])
  rack_data = rack_data_prefix + ','.join([str(node) for node in rack_nodes])

hostfile="ordered_hostfile"
write_ordered_hostfile(ordered_hosts,hostfile)
hostfile="ordered_hostfile_system_name"
write_ordered_hostfile(ordered_hosts_friendly_name,hostfile)
rankfile="rankfile_system_name"
write_ordered_rankfile(ordered_hosts_friendly_name,rankfile)

