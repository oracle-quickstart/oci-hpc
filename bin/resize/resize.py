import sys
import oci
import subprocess
import json
import time
import requests
import argparse
import shutil
import os
import copy
import ipaddress
from datetime import datetime
from ociobj import ocicore, ocicluster
from utils import get_metadata, wait_for_running_status, get_instances, parse_inventory, getNFSnode, get_summary, updateTFState, getreachable, getLaunchInstanceDetails, check_replace_slumhostname
from reconfigure import destroy_unreachable_reconfigure, add_reconfigure, reconfigure

batchsize=12
inventory="/etc/ansible/hosts"
playbooks_dir="/opt/oci-hpc/playbooks/"
hostfile="/etc/hosts"

parser = argparse.ArgumentParser(description='Script to resize the CN')
parser.add_argument('--compartment_ocid', help='OCID of the compartment, defaults to the Compartment OCID of the localhost')
parser.add_argument('--cluster_name', help='Name of the cluster to resize. Defaults to the name included in the controller')
parser.add_argument('mode', help='Mode type. add/remove node options, implicitly configures newly added nodes. Also implicitly reconfigure/restart services like Slurm to recognize new nodes. Similarly for remove option, \
                    terminates nodes and implicitly reconfigure/restart services like Slurm on rest of the cluster nodes to remove reference to deleted nodes. \
                    IMPORTANT: remove or remove_unreachable means delete the node from the cluster which means terminate the node. remove_unreachable should be used to remove specific nodes which are no longer reachable via ssh. \
                    It gives you control on which nodes will be terminated by passing the --nodes parameter. ',choices=['add','remove','remove_unreachable','list','reconfigure'],default='list',nargs='?')
parser.add_argument('number', type=int, help="Number of nodes to add or delete if a list of hostnames is not defined",nargs='?')
parser.add_argument('--nodes', help="List of nodes to delete (Space Separated)",nargs='+')
parser.add_argument('--no_reconfigure', help='If present. Does not rerun the playbooks',action='store_true',default=False)
parser.add_argument('--user_logging', help='If present. Use the default settings in ~/.oci/config to connect to the API. Default is using instance_principal',action='store_true',default=False)
parser.add_argument('--force', help='If present. Nodes will be removed even if the destroy playbook failed',action='store_true',default=False)
parser.add_argument('--ansible_crucial', help='If present during reconfiguration, only crucial ansible playbooks will be executed on the live nodes. Non live nodes will be removed',action='store_true',default=False)
parser.add_argument('--remove_unreachable', help='If present, ALL nodes that are not sshable will be terminated before running the action that was requested (Example Adding a node). \
                    CAUTION: Use this only if you want to remove ALL nodes that are unreachable. Instead, remove specific nodes that are unreachable by using positional argument remove_unreachable.',action='store_true',default=False)
parser.add_argument('--quiet', help='If present, the script will not prompt for a response when removing nodes and will not give a reminder to save data from nodes that are being removed ',action='store_true',default=False)

args = parser.parse_args()

metadata=get_metadata()
if args.compartment_ocid is None:
    comp_ocid=metadata['compartmentId']
else:
    comp_ocid=args.compartment_ocid

if args.cluster_name is None:
    cluster_name=metadata['displayName'].replace('-controller','')
else:
    cluster_name=args.cluster_name

if cluster_name == metadata['displayName'].replace('-controller',''):
    inventory="/etc/ansible/hosts"
    host_check_file="/tmp/hosts"
    autoscaling=False
else:
    inventory= "/opt/oci-hpc/autoscaling/clusters/"+cluster_name+'/inventory'
    host_check_file="/opt/oci-hpc/autoscaling/clusters/"+cluster_name+'/hosts_'+cluster_name
    autoscaling = True

inventory_dict = parse_inventory(inventory)
username="opc"
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("compute_username"):
        username=inv_vars.split("compute_username=")[1].strip()
        break
zone_name=cluster_name+".local"
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("zone_name"):
        zone_name=inv_vars.split("zone_name=")[1].strip()
        break
dns_entries=True
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("dns_entries"):
        dns_entries=(inv_vars.split("dns_entries=")[1].strip().lower() == "true")
        break
vcn_compartment=comp_ocid
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("vcn_compartment"):
        vcn_compartment=inv_vars.split("vcn_compartment=")[1].strip()
        break
hostname_convention=None
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("hostname_convention"):
        hostname_convention=inv_vars.split("hostname_convention=")[1].strip()
        break
instance_type=""
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("instance_type"):
        instance_type=inv_vars.split("instance_type=")[1].strip()
        break
private_subnet_cidr=None
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("private_subnet"):
        private_subnet_cidr=ipaddress.ip_network(inv_vars.split("private_subnet=")[1].strip())
        break
slurm_name_change=None
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("change_hostname"):
        slurm_name_change=(inv_vars.split("change_hostname=")[1].strip().lower() == "true")
        break

hostnames=args.nodes
if hostnames is None:
    hostnames=[]

if args.mode=='remove' and args.number is None and args.nodes is None:
    print("STDOUT: No Nodes to remove")
    exit(1)

if args.mode=='add' and args.number is None:
    print("STDOUT: No Nodes to add")
    exit(1)

if args.no_reconfigure is None:
    no_reconfigure=False
else:
    no_reconfigure=args.no_reconfigure

if args.user_logging is None:
    user_logging=False
else:
    user_logging=args.user_logging

if args.force is None:
    force=False
else:
    force=args.force

if args.ansible_crucial is None:
    ansible_crucial=False
else:
    ansible_crucial=args.ansible_crucial

if args.remove_unreachable is None:
    remove_unreachable=False
else:
    remove_unreachable=args.remove_unreachable

ocicore = ocicore(user_logging)

cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name,ocicore)
if cn_summary is None:
    exit(1)
cn_ocid =cn_summary.id

if CN != "CC":
    current_size=ip_summary.size
    if CN == "CN":
        ipa_ocid = cn_summary.instance_pools[0].id
    else:
        ipa_ocid = cn_ocid

ocicluster = ocicluster(comp_ocid, cn_ocid, CN, cluster_name, username, inventory, hostfile, \
                        playbooks_dir, slurm_name_change, hostname_convention, autoscaling)

if args.mode == 'list':
    state = cn_summary.lifecycle_state
    print("Cluster is in state:"+state )
    cn_instances = get_instances(ocicluster, ocicore)
    for cn_instance in cn_instances:
        print(cn_instance['display_name']+' '+cn_instance['ip']+' '+cn_instance['ocid'])
elif args.mode == 'reconfigure':
    if len(hostnames)>0:
        add_reconfigure(ocicluster,ocicore,specific_hosts=hostnames)
    else:
        reconfigure(ocicluster,ocicore,crucial=ansible_crucial)
else:
    wait_for_running_status(ocicluster,ocicore)
    cn_instances = get_instances(ocicluster, ocicore)
    inventory_instances =[]
    only_inventory_instance=[]
    if dns_entries:
        zone_id=ocicore.dns_client.list_zones(compartment_id=vcn_compartment,name=zone_name,zone_type="PRIMARY",scope="PRIVATE").data[0].id
    for line in inventory_dict['compute_configured']:
        host=line.split('ansible_host=')[0].strip()
        ip=line.split("ansible_host=")[1].split("ansible_user=")[0].strip()
        inventory_instances.append({'display_name':host,'ip':ip,'ocid':None})
        if not host in [i['display_name'] for i in cn_instances]:
            ip=line.split("ansible_host=")[1].split("ansible_user=")[0].strip()
            print("STDOUT: "+host+" with IP: "+ip+" is in the inventory but not in the cluster")
            only_inventory_instance.append({'display_name':host,'ip':ip,'ocid':None})
    for line in inventory_dict['compute_to_add']:
        host=line.split('ansible_host=')[0].strip()
        ip=line.split("ansible_host=")[1].split("ansible_user=")[0].strip()
        inventory_instances.append({'display_name':host,'ip':ip,'ocid':None})
        if not host in [i['display_name'] for i in cn_instances]:
            print("STDOUT: "+host+" with IP: "+ip+" is in the inventory but not in the cluster")
            only_inventory_instance.append({'display_name':host,'ip':ip,'ocid':None})
    if args.mode == 'remove_unreachable':
        if len(hostnames) == 0:
            reachable_instances,unreachable_instances=getreachable(cn_instances+only_inventory_instance,ocicluster,delay=10)
            if len(unreachable_instances):
                hostnames_to_remove=[i['display_name'] for i in unreachable_instances]
            else:
                print("STDOUT: No list of nodes were specified and no unreachable nodes were found")
                exit(1)
        else:
            inventory_instances_to_test = []
            for instance_to_test in inventory_instances:
                if not instance_to_test['display_name'] in hostnames:
                    inventory_instances_to_test.append(instance_to_test)
            reachable_instances,unreachable_instances=getreachable(inventory_instances_to_test,ocicluster,delay=10)
            hostnames_to_remove=hostnames
            if len(unreachable_instances):
                print("STDOUT: At least one unreachable node is in the inventory and was not mentionned with OCI hostname to be removed. Trying anyway")
    else:
        reachable_instances,unreachable_instances=getreachable(inventory_instances,ocicluster,delay=10)
        if len(unreachable_instances):
            if not remove_unreachable:
                print("STDOUT: At least one unreachable node is in the inventory")
                print(unreachable_instances)
                print("STDOUT: Not doing anything")
                exit(1)
            else:
                hostnames_to_remove=[i['display_name'] for i in unreachable_instances]
        else:
            hostnames_to_remove=[]
    if args.mode == 'remove':
        if len(hostnames) == 0:
            nfsNode=getNFSnode(inventory)
            non_nfs=[i for i in cn_instances if i['display_name'] != nfsNode]
            additional_nodes_to_remove_number=args.number-len(hostnames_to_remove)
            if additional_nodes_to_remove_number > 0:
                if additional_nodes_to_remove_number < len(cn_instances):
                    hostnames_to_remove=hostnames_to_remove+[non_nfs[i]['display_name'] for i in range(len(non_nfs)-additional_nodes_to_remove_number,len(non_nfs))]
                else:
                    hostnames_to_remove=[cn_instances[i]['display_name'] for i in range(len(cn_instances))]
        else:
            hostnames_to_remove2 = list(hostnames)
            hostnames_to_remove2.extend(x for x in hostnames_to_remove if x not in hostnames_to_remove2)
            hostnames_to_remove=hostnames_to_remove2

    if slurm_name_change:
        hostnames_to_remove = check_replace_slumhostname(hostnames_to_remove, cn_instances, ocicluster)

    hostnames_to_remove_len=len(hostnames_to_remove)

    if hostnames_to_remove_len:
        print(f"STDOUT: Trying to terminate nodes {hostnames_to_remove}")
        if not no_reconfigure:
            playbook = playbooks_dir+"resize_remove_unreachable.yml"
            error_code = destroy_unreachable_reconfigure(ocicluster,ocicore,hostnames_to_remove,playbook)
            if error_code != 0:
                print("STDOUT: The nodes could not be removed. Try running this with Force")
                if not force:
                    exit(1)
                else:
                    print("STDOUT: Force deleting the nodes")
        terminated_instances=0
        cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name,ocicore)
        if CN != "CC":
            current_size = ip_summary.size
        for instanceName in hostnames_to_remove:
            try:
                instance_id = ocicore.computeClient.list_instances(comp_ocid,display_name=instanceName).data[0].id
                if CN == "CC":
                    ocicore.ComputeClientCompositeOperations.terminate_instance_and_wait_for_state(instance_id,wait_for_states=["TERMINATING","TERMINATED"])
                else:
                    instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=instance_id,is_auto_terminate=True,is_decrement_size=True)
                    ocicore.ComputeManagementClientCompositeOperations.detach_instance_pool_instance_and_wait_for_work_request(ipa_ocid,instance_details)
                if dns_entries:
                    get_rr_set_response = ocicore.dns_client.delete_rr_set(zone_name_or_id=zone_id,domain=instanceName+"."+zone_name,rtype="A",scope="PRIVATE")
                    ip=None
                    for i in cn_instances:
                        if i['display_name'] == instanceName:
                            ip = ipaddress.ip_address(i['ip'])
                    if not ip is None:
                        index = list(private_subnet_cidr.hosts()).index(ip)+2
                        slurm_name=hostname_convention+"-"+str(index)+"."+zone_name
                        get_rr_set_response = ocicore.dns_client.delete_rr_set(zone_name_or_id=zone_id,domain=slurm_name,rtype="A",scope="PRIVATE")
                terminated_instances = terminated_instances + 1
                print("STDOUT: The instance "+instanceName+" is terminating")
            except:
                print("STDOUT: The instance "+instanceName+" does not exist")
        cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name,ocicore)
        if CN == "CC":
            instance_id = ocicore.computeClient.list_instances(comp_ocid,display_name=hostnames_to_remove[-1]).data[0].id
            for i in range(10):
                try:
                    instance_state = ocicore.computeClient.get_instance(instance_id).data.lifecycle_state
                    if instance_state == "TERMINATED":
                        break
                    else:
                        time.sleep(10)
                except:
                    break
            cn_instances = get_instances(ocicluster,ocicore)
            newsize=len(cn_instances)
        else:
            newsize=ip_summary.size
            updateTFState(inventory,cluster_name,newsize)
        print("STDOUT: Resized to "+str(newsize)+" instances")
#        if error_code != 0 and force:
#            print("STDOUT: The nodes were forced deleted, trying to reconfigure the left over nodes")
#            reconfigure(comp_ocid,cn_ocid,inventory,CN)

    if args.mode == 'add':
        cn_instances = get_instances(ocicluster,ocicore)
        if CN == "CC":
            current_size=len(cn_instances)
            if len(cn_instances) == 0:
                print("STDOUT: The resize script cannot work for a compute cluster if the size is there is no node in the cluster")
            else:
                for cn_instance in cn_instances:
                    max_index=-1
                    if int(cn_instance['display_name'].split('-')[-1]) > max_index:
                        max_index=int(cn_instance['display_name'].split('-')[-1])
                instance=ocicore.computeClient.get_instance(cn_instances[0]['ocid']).data
                print("STDOUT: Provisioning instances")
                for i in range(args.number):
                    launch_instance_details=getLaunchInstanceDetails(instance,comp_ocid,cn_ocid,max_index,i)
                    ocicore.ComputeClientCompositeOperations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
        else:
            size = current_size - hostnames_to_remove_len + args.number
            update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
            print("STDOUT: Provisioning instances")
            ocicore.ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(ipa_ocid,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
        cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name,ocicore)
        if CN == "CC":
            new_cn_instances = get_instances(ocicluster,ocicore)
            newsize=len(new_cn_instances)
        else:
            new_cn_instances = get_instances(ocicluster,ocicore)
            newsize=ip_summary.size
        if dns_entries:
            for new_instance in new_cn_instances:
                if not new_instance in cn_instances:
                    instanceName=new_instance['display_name']
                    ip = ipaddress.ip_address(new_instance['ip'])
                    index = list(private_subnet_cidr.hosts()).index(ip)+2
                    slurm_name=hostname_convention+"-"+str(index)+"."+zone_name
                    get_rr_set_response = ocicore.dns_client.update_rr_set(zone_name_or_id=zone_id,domain=slurm_name,rtype="A",scope="PRIVATE",update_rr_set_details=oci.dns.models.UpdateRRSetDetails(items=[oci.dns.models.RecordDetails(domain=slurm_name,rdata=new_instance['ip'],rtype="A",ttl=3600,)]))
                    get_rr_set_response = ocicore.dns_client.update_rr_set(zone_name_or_id=zone_id,domain=instanceName+"."+zone_name,rtype="A",scope="PRIVATE",update_rr_set_details=oci.dns.models.UpdateRRSetDetails(items=[oci.dns.models.RecordDetails(domain=instanceName+"."+zone_name,rdata=new_instance['ip'],rtype="A",ttl=3600)]))
        updateTFState(inventory,cluster_name,newsize)
        if newsize == current_size:
            print("STDOUT: No node was added, please check the work requests of the Cluster Network and Instance Pool to see why")
            exit(1)
        if not no_reconfigure:
            print("STDOUT: Configuring nodes")
            add_reconfigure(ocicluster,ocicore)