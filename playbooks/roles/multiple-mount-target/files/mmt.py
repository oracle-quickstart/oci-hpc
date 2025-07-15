#!/usr/bin/env python3
import sys
import json
import re
import argparse
import warnings 
warnings.filterwarnings(action='ignore',module='.*paramiko.*')
import paramiko
import subprocess
import os
import requests

def distribute_new_mt_assignments(new_nodes, mt_distribution, current_nodes, args_nfs_path):
  assignments = dict()
  for node in new_nodes:
    open_mt = min(mt_distribution, key=mt_distribution.get)
    assignments[node] = open_mt
    mt_distribution[open_mt] += 1
  return assignments

def get_mt_distribution(current_nodes, mount_targets, args_nfs_path): 
  mt_distribution = {key: 0 for key in mount_targets}
  for node in current_nodes:
    mt_ip = get_fstab_entry_ip(node, args_nfs_path)
    if mt_ip == None: continue
    try: 
      mt_distribution[mt_ip] += 1
    except KeyError:
      mt_distribution[mt_ip] = 1
  return mt_distribution

def get_fstab_entry_ip(node, args_nfs_path): 
  ip_regex = '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'
  cmd = "sudo grep " + args_nfs_path + " /etc/fstab"
  ssh_user = os.getlogin()
  private_keyfile = "/home/" + ssh_user + "/.ssh/cluster.key"
  try:
    key = paramiko.Ed25519Key.from_private_key_file(private_keyfile)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    port = 22
    ip = None
    client.connect(hostname=node, username=ssh_user, pkey=key, port=port)
    _, stdout, stderr = client.exec_command(cmd)
    output = stdout.read().decode("utf-8")
    error = stderr.read().decode()
    if error:
      print("Error:\n", error)
      sys.exit(-1)
    reg_search = re.search(ip_regex, output)
    if reg_search is not None:
      ip = reg_search.group()
  except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(-1)
  finally:
    client.close()
  return ip

def remove_spaces_and_convert_to_list(mt):
  return [item.strip() for item in mt.split(',')]

def get_metadata():
  """ Make a request to metadata endpoint """
  headers = { 'Authorization' : 'Bearer Oracle' }
  metadata_url = "http://169.254.169.254/opc/"
  metadata_ver = "2"
  request_url = metadata_url + "v" + metadata_ver + "/instance/"
  return requests.get(request_url, headers=headers).json()

def parse_inventory(inventory):
  try:
      inv = open(inventory,"r")
  except:
      return None
  inventory_dict = {}
  current_section = None
  for line in inv:
      if line.strip().startswith("[") and line.strip().endswith("]"):
          current_section=line.split('[')[1].split(']')[0]
          if not current_section in inventory_dict.keys():
              inventory_dict[current_section]=[]
      else:
          if not current_section is None:
              inventory_dict[current_section].append(line)
  inv.close()
  return inventory_dict

def getClusterNames():
  out = subprocess.Popen(["ls /opt/oci-hpc/autoscaling/clusters/"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
  stdout,stderr = out.communicate()
  x = stdout.split("\n")
  del x[-1]
  cluster_name_set = set()
  for i in range(len(x)):
    if x[i] == 'README':
      continue
    else:
      cluster_name_set.add(x[i])
  return cluster_name_set

def getNodesInClusters(metadata, cluster_name):
  nodes = []
  permanent_cluster = metadata['displayName'].replace('-controller','')
  if cluster_name == permanent_cluster:
    inventory = "/etc/ansible/hosts"
    inventory_dict = parse_inventory(inventory)
    inv_list = inventory_dict["compute_configured"]
    for i in inv_list:
      split_str = i.split()
      node_name = split_str[0]
      nodes.append(node_name)
  else:
    inventory = "/opt/oci-hpc/autoscaling/clusters/"+cluster_name+"/inventory"
    inventory_dict = parse_inventory(inventory)
    inv_list = inventory_dict["compute_configured"]
    for i in inv_list:
      split_str = i.split()
      node_name = split_str[0]
      nodes.append(node_name)
  return nodes

def main():
  parser = argparse.ArgumentParser(
                       prog='Multiple Mount Target Distribution',
                       description='Distributes multiple FSS mount targets for all the nodes in all clusters')
  parser.add_argument('-n', '--new', default=[], nargs='*', help="nodes to be assigned mount target")
  parser.add_argument('-c', '--current', default=[], nargs='*', help="controller, login, backup nodes. During first time stack creation, this will be empty")
  parser.add_argument('-m', '--mount_targets', help="Comma separated string with mount target IPs")
  parser.add_argument('-nfs', '--nfs_path', help="Value of the FSS path on the NFS server")
  
  args = parser.parse_args()
  args_new_nodes = args.new 
  args_current_nodes = args.current 
  args_mount_targets = args.mount_targets
  mount_targets_list = remove_spaces_and_convert_to_list(args_mount_targets)
  args_nfs_path = args.nfs_path

  if args_new_nodes == ['{}']:
    print("There was no input for new nodes to be assigned mount targets. Exiting.")
    sys.exit(-1)
  else:
    joined_args_new_nodes = ''.join(args_new_nodes)
    new_nodes = joined_args_new_nodes.strip("[").strip("]").strip(",").split(',')
    if len(new_nodes) == 0:
      print("There was no input for new nodes to be assigned mount targets. Exiting.")
      sys.exit(-1)
    else:
      if args_current_nodes == ['{}']:
        current_nodes = []
      else:
        joined_args_current_nodes = ''.join(args_current_nodes)
        current_nodes = joined_args_current_nodes.strip("[").strip("]").strip(",").split(',')

      cluster_names_list = getClusterNames()
      metadata=get_metadata()
      cluster_names_list.add(metadata['displayName'].replace('-controller',''))
      for cluster in cluster_names_list:
        nodes = getNodesInClusters(metadata, cluster)
        current_nodes.extend(nodes)
      mt_distribution = get_mt_distribution(current_nodes, mount_targets_list, args_nfs_path)
      assignments = distribute_new_mt_assignments(new_nodes, mt_distribution, current_nodes, args_nfs_path)
      
      output_mt_assignments = []
      
      if assignments:
        for node, mt in assignments.items():
          output_mt_assignments.append({'host': node, 'mount_target': mt}) 
        json.dump(output_mt_assignments,sys.stdout) 
      else:
        print("There was error assigning mount target to nodes. Please check and proceed. ")
        sys.exit(-1)

if __name__ == '__main__':
  main()