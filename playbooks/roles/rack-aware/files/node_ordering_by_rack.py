#!/usr/bin/env python3
import json
import os
import argparse
import subprocess

def write_ordered_hostfile(ordered_hosts=[],hostfile=None,srun=False):
   #ordered_hostfile="ordered_hostfile"
   if os.path.isfile(hostfile):
      os.remove(hostfile)
   fhandler = open(hostfile,"w")
   for h in ordered_hosts:
      if srun:
        for x in range(8):
          fhandler.write(h+"\n")
      else:
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


r = {}
friendly_name_to_system_hostname = {}
try:
    from pssh.clients import ParallelSSHClient
    client = ParallelSSHClient(hosts)
    output = client.run_command('curl http://169.254.169.254/opc/v1/host/')
    for host_out in output:
        j = json.loads(bytearray(''.join(list(host_out.stdout)).encode()))
        if j['rackId'] in r:
            r[j['rackId']].append( host_out.host )
        else:
            r[j['rackId']] = [ host_out.host ]
    hostname_output = client.run_command('/usr/bin/hostname')
    for host_out in hostname_output:
        j = bytearray(''.join(list(host_out.stdout)).encode())
        friendly_name_to_system_hostname[host_out.host] = j.decode(encoding='ascii')
        #print(j.decode(encoding='ascii')+"   "+host_out.host)
except ImportError:
    try:
        for h in hosts:
            out = subprocess.run(["ssh "+h+" \"curl -s http://169.254.169.254/opc/v1/host/\""],stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, universal_newlines=True, check=True)
            x = out.stdout.splitlines()
            del x[-1]
            del x[0]
            rackId_str = x[1].split(":")[1].replace('"','')
            rackId = rackId_str.replace(' ','')
            if rackId in r:
                r[rackId].append( h )
            else:
                r[rackId] = [ h ]
        for h in hosts:
            out = subprocess.run(["ssh "+h+" /usr/bin/hostname"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, universal_newlines=True, check=True)
            x = out.stdout.splitlines()
            friendly_name_to_system_hostname[h] = x[0]
    except subprocess.CalledProcessError as e_process_error:
        exit(f"Error code: {e_process_error.returncode} Output: {e_process_error.output}")


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
hostfile="ordered_hostfile_system_name_srun"
write_ordered_hostfile(ordered_hosts_friendly_name,hostfile,True)
rankfile="rankfile_system_name"
write_ordered_rankfile(ordered_hosts_friendly_name,rankfile)

