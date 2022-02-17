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
from datetime import datetime

def get_metadata():
    """ Make a request to metadata endpoint """
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()

def wait_for_running_status(cluster_name,comp_ocid,cn_ocid,expected_size=None):
    while True:
        state=computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data[0].lifecycle_state
        instances=computeManagementClient.list_cluster_network_instances(comp_ocid,cn_ocid).data
        if state != 'RUNNING':
            print("Cluster state is "+state+", cannot add or remove nodes")
            print ("Waiting...")
            time.sleep(30)
        elif not expected_size is None:
            if expected_size == len(instances):
                break
            else:
                print("The instance list does not match the expected size")
                time.sleep(30)
        else:
            break
    return True

def get_instances(comp_ocid,cn_ocid):
    cn_instances=[]
    for instance_summary in oci.pagination.list_call_get_all_results(computeManagementClient.list_cluster_network_instances,comp_ocid,cn_ocid).data:
        try:
            instance=computeClient.get_instance(instance_summary.id).data
            vnic_attachment = oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=comp_ocid,instance_id=instance.id).data[0]
            vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
        except:
            continue
        cn_instances.append({'display_name':instance_summary.display_name,'ip':vnic.private_ip})
    return cn_instances

def create_temp_inventory_file(comp_ocid,cn_ocid,inventory,hostnames=[],slurm_only_update='false'):
    instances = get_instances(comp_ocid,cn_ocid)
    nodes_to_not_reconfigure=copy.deepcopy(instances)
    if not os.path.isfile("/etc/ansible/hosts"):
        print("There is no inventory file, are you on the bastion? The cluster has been resized but not reconfigured")
        exit()
    elif len(instances) == 0:
        print("The cluster is now empty, not reconfiguring")
        exit()
    else :
        tmp_reconfigure_some_nodes_inv_file_do_not_edit="/tmp/resize_reconfigure_some_nodes_ansible_inventory"
        old_inv=open("/etc/ansible/hosts","r")
        old_nodes=[]
        nodes_to_reconfigure=[]
        get=False
        for line in old_inv:
            if get:
                if line.strip().startswith("[") and line.strip().endswith("]"):
                    get=False
                else:
                    for node in instances:
                        if node['display_name'] in line and node['ip'] in line:
                            for hostname in hostnames:
                                if node['display_name'] == hostname:
                                    nodes_to_reconfigure.append(node)
                                    nodes_to_not_reconfigure.remove(node)
                            old_nodes.append(line)
                            break
            elif "[compute]" in line:
                get=True
        if len(nodes_to_reconfigure) == len(hostnames):
            print("found all nodes to be reconfigured in the running cluster")
        else:
            print("Cannot find all nodes passed in the command in running cluster"+", only "+str(len(nodes_to_reconfigure))+" were found")
            exit()
        old_inv.close()
        inv_file=open(inventory,'r')
        #hosts_file=open("/tmp/hosts",'w')
        tmp_file=open(tmp_reconfigure_some_nodes_inv_file_do_not_edit,'w')
        #tmp_file_do_not_edit="/tmp/etc_ansible_hosts.do_not_edit"
        #shutil.copyfile("/etc/ansible/hosts",tmp_file_do_not_edit)
        replace=False
        for line in inv_file:
            if "[compute]" in line:
                tmp_file.write(line)
                replace=True
                for line in old_nodes:
                    tmp_file.write(line)
                tmp_file.write("[exclude]"+"\n")
                for node in nodes_to_not_reconfigure:
                    tmp_file.write(node['display_name']+" ansible_host="+node['ip']+" ansible_user=opc role=compute\n")
            elif "[nfs]" in line:
                 replace=False
            elif "[all:children]" in line:
                 replace=False
            elif "[exclude]" in line:
                 replace=True

            if not replace:
                tmp_file.write(line)

        inv_file.close()
        tmp_file.close()
        #hosts_file.close()
        #shutil.move("/tmp/hosts_ansible",inventory)








def modify_inventory_file(comp_ocid,cn_ocid,inventory):
    instances = get_instances(comp_ocid,cn_ocid)
    nodes_to_add=copy.deepcopy(instances)
    if not os.path.isfile("/etc/ansible/hosts"):
        print("There is no inventory file, are you on the bastion? The cluster has been resized but not reconfigured")
        exit()
    elif len(instances) == 0:
        print("The cluster is now empty, not reconfiguring")
        exit()
    else :
        # Returns a datetime object containing the local date and time
        dateTimeObj = datetime.now()
        timestampStr = dateTimeObj.strftime("%d-%b-%Y-%H-%M-%S-%f")
        backup_ansible_hosts="/tmp/etc_ansible_hosts"+"."+timestampStr
        shutil.copyfile("/etc/ansible/hosts",backup_ansible_hosts)
        tmp_file_do_not_edit="/tmp/etc_ansible_hosts.do_not_edit"
        if os.path.isfile(tmp_file_do_not_edit):
            print("File "+tmp_file_do_not_edit+" exist, it means previous reconfigure had failed. Hence updating /etc/ansible/hosts to previous state")
            shutil.move(tmp_file_do_not_edit,inventory)
        old_inv=open("/etc/ansible/hosts","r")
        old_nodes=[]
        get=False
        for line in old_inv:
            if get:
                if line.strip().startswith("[") and line.strip().endswith("]"):
                    get=False
                else:
                    for node in instances:
                        if node['display_name'] in line and node['ip'] in line:
                            old_nodes.append(line)
                            print("node="+node['display_name'])
                            nodes_to_add.remove(node)
                            break
            elif "[compute]" in line:
                get=True
        old_inv.close()
        inv_file=open(inventory,'r')
        hosts_file=open("/tmp/hosts",'w')
        tmp_file=open("/tmp/hosts_ansible",'w')
        shutil.copyfile("/etc/ansible/hosts",tmp_file_do_not_edit)
        replace=False
        for line in inv_file:
            if "[compute]" in line:
                tmp_file.write(line)
                replace=True
                for line in old_nodes:
                    tmp_file.write(line)
                for node in nodes_to_add:
                    tmp_file.write(node['display_name']+" ansible_host="+node['ip']+" ansible_user=opc role=compute\n")
                    hosts_file.write(node['ip']+"\n")
                tmp_file.write("[exclude]"+"\n")
                for line in old_nodes:
                    tmp_file.write(line)
            elif "[nfs]" in line:
                 replace=False
            elif "[all:children]" in line:
                 replace=False
            elif "[exclude]" in line:
                 replace=True

            if not replace:
                tmp_file.write(line)

        inv_file.close()
        tmp_file.close()
        hosts_file.close()
        shutil.move("/tmp/hosts_ansible",inventory)


def update_cluster(mode,hostnames=[],slurm_only_update='false'):
    inv_file="/etc/ansible/hosts"
    tmp_file_do_not_edit="/tmp/etc_ansible_hosts.do_not_edit"
    if mode == 'reconfigure':
        if len(hostnames) > 0:
            playbook="resize_add_nodes.yml"
            inv_file="/tmp/resize_reconfigure_some_nodes_ansible_inventory"
        elif (slurm_only_update == 'true'):
            playbook="resize_slurm_only_update.yml"
        else:
            playbook="site.yml"
            #exit()
    elif mode == 'add':
        playbook="resize_add_nodes.yml"
    elif mode == 'remove':
        playbook="resize_slurm_only_update.yml"
    else:
        print("mode is invalid")
        exit()

    my_env = os.environ.copy()
    my_env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    rc = 0
    p = subprocess.Popen(["/opt/oci-hpc/bin/configure.sh",playbook,inv_file],env=my_env,stderr = subprocess.PIPE, stdout=subprocess.PIPE)
    while True:
        output = p.stdout.readline().decode()
        if output == '' and p.poll() is not None:
            break
        if output:
            print(output.strip())
    rc = p.returncode 
    if (rc == 0):
        print("success")
        if os.path.isfile(tmp_file_do_not_edit):
            #print("file exist "+tmp_file_do_not_edit+" now deleting ")
            os.remove(tmp_file_do_not_edit)
    else:
        print("return code from ansible playbook job was non-zero, review what failed during ansible tasks run : "+str(rc))
        if os.path.isfile(tmp_file_do_not_edit):
            shutil.move(tmp_file_do_not_edit, "/tmp/etc_ansible_hosts.do_not_edit.old")
        print("Resolve the issue which caused ansible playbook to fail (hint: look for word fatal in above output). Then run the below command to only run the reconfigure step (ansible playbook) without again adding or removing node from HPC/GPU cluster.")
        if mode == 'add':
            print("Command:  python3 playbooks/resize.py reconfigure --nodes newly_added_node1_hostname newly_added_node2_hostname ")
        if mode == 'remove':
            print("Command:  python3 playbooks/resize.py reconfigure --slurm_only_update true ")


batchsize=12
inventory="/etc/ansible/hosts"

parser = argparse.ArgumentParser(description='Script to resize the CN')
parser.add_argument('--compartment_ocid', help='OCID of the compartment, defaults to the Compartment OCID of the localhost')
parser.add_argument('--cluster_name', help='Name of the cluster to resize. Defaults to the name included in the bastion')
parser.add_argument('mode', help='Mode type. add/remove node options, implicitly configures newly added nodes. Also implicitly reconfigure/restart services like Slurm to recognize new nodes. Similarly for remove option, terminates nodes and implicitly reconfigure/restart services like Slurm on rest of the cluster nodes to remove reference to deleted nodes.',choices=['add','remove','list','reconfigure'],default='list',nargs='?')
parser.add_argument('number', type=int, help="Number of nodes to add or delete if a list of hostnames is not defined",nargs='?')
parser.add_argument('--nodes', help="Number of nodes to add or delete if a list of hostnames is not defined",nargs='+')
parser.add_argument('--slurm_only_update', help='To update /etc/hosts, slurm config and restart slurm services.',choices=['true','false'],default='false',nargs='?')
args = parser.parse_args()


metadata=get_metadata()
if args.compartment_ocid is None:
    comp_ocid=metadata['compartmentId']
else:
    comp_ocid=args.compartment_ocid

if args.cluster_name is None:
    cluster_name=metadata['displayName'].replace('-bastion','')
else:
    cluster_name=args.cluster_name
hostnames=args.nodes
if hostnames is None:
    hostnames=[]

if args.mode=='remove' and args.number is None and args.nodes is None:
    print("No Nodes to remove")
    exit()

if args.mode=='add' and args.number is None:
    print("No Nodes to add")
    exit()


if args.slurm_only_update is None:
    slurm_only_update='false'
else:
    slurm_only_update=args.slurm_only_update



signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
computeClient = oci.core.ComputeClient(config={}, signer=signer)
computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=signer)
ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(computeManagementClient)
virtualNetworkClient = oci.core.VirtualNetworkClient(config={}, signer=signer)

cn_summaries = computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data
running_clusters = 0
for cn_summary_tmp in cn_summaries:
    if cn_summary_tmp.lifecycle_state == "RUNNING":
        cn_summary = cn_summary_tmp
        running_clusters = running_clusters + 1
if running_clusters == 0:
    print("The cluster was not found")
elif running_clusters > 1:
    print("There were multiple running clusters with this name, we selected the one with OCID:"+cn_summary.id)

cn_ocid =cn_summary.id
ipa_ocid = computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data[0].instance_pools[0].id
current_size = computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data[0].instance_pools[0].size

if args.mode == 'list':
    state=computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data[0].lifecycle_state
    print("Cluster is in state:"+state )
    cn_instances = get_instances(comp_ocid,cn_ocid)
    for cn_instance in cn_instances:
        print(cn_instance['display_name']+' '+cn_instance['ip'])
elif args.mode == 'reconfigure':
    create_temp_inventory_file(comp_ocid,cn_ocid,inventory,hostnames,slurm_only_update)
    update_cluster(args.mode,hostnames,slurm_only_update)
else:
    #update_cluster(args.mode,hostnames,slurm_only_update)
    #exit()
    wait_for_running_status(cluster_name,comp_ocid,cn_ocid)
    if args.mode == 'add' or (args.mode == 'remove' and len(hostnames) == 0):
        if args.mode == 'add':
            size = current_size + args.number
        else:
            size = current_size - args.number
        update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
        ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(ipa_ocid,update_size,['RUNNING'])
    else:
        while len(hostnames) > 0:
            terminated_instances=0
            if len(hostnames) >batchsize:
                batch = hostnames[:batchsize]
            else:
                batch = hostnames
            current_size = computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data[0].instance_pools[0].size
            for instanceName in batch:
                try:
                    instance_id = computeClient.list_instances(comp_ocid,display_name=instanceName).data[0].id
                    instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=instance_id,is_auto_terminate=True,is_decrement_size=True)
                    print("The instance "+instanceName+" is terminating")
                    ComputeManagementClientCompositeOperations.detach_instance_pool_instance_and_wait_for_work_request(ipa_ocid,instance_details)
                    terminated_instances = terminated_instances + 1
                except:
                    print("The instance "+instanceName+" does not exist")
            hostnames=hostnames[batchsize:]
            if len(hostnames)>0:
                time.sleep(100)
        newsize = computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data[0].instance_pools[0].size
        print("Resized to "+str(newsize)+" instances")
    modify_inventory_file(comp_ocid,cn_ocid,inventory)
    update_cluster(args.mode,hostnames,slurm_only_update)
