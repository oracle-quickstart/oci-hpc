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

def wait_for_running_status(cluster_name,comp_ocid,cn_ocid,CN,expected_size=None):
    while True:
        if CN:
            state = computeManagementClient.get_cluster_network(cn_ocid).data.lifecycle_state
            instances=computeManagementClient.list_cluster_network_instances(comp_ocid,cn_ocid).data
        else:
            state = computeManagementClient.get_instance_pool(cn_ocid).data.lifecycle_state
            instances=computeManagementClient.list_instance_pool_instances(comp_ocid,cn_ocid).data
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

def get_instances(comp_ocid,cn_ocid,CN):
    cn_instances=[]
    if CN:
        instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_cluster_network_instances,comp_ocid,cn_ocid).data
    else:
        instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_instance_pool_instances,comp_ocid,cn_ocid).data
    for instance_summary in instance_summaries:
        try:
            instance=computeClient.get_instance(instance_summary.id).data
            for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=comp_ocid,instance_id=instance.id).data:
                if potential_vnic_attachment.display_name is None:
                    vnic_attachment = potential_vnic_attachment
            vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
        except:
            continue
        cn_instances.append({'display_name':instance_summary.display_name,'ip':vnic.private_ip,'ocid':instance_summary.id})
    return cn_instances

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

def write_inventory(dict,inventory):
    inv = open(inventory,"w")
    for section in dict.keys():
        inv.write("["+section+"]\n")
        for line in dict[section]:
            inv.write(line)
    inv.close()

def remove_ip(filename,iplist):
    tmp_filename=os.path.join('/tmp',os.path.basename(filename))
    hostFile = open(filename,"r")
    hostFile_tmp = open(tmp_filename,"w")
    for line in hostFile:
        if not line.strip() in iplist:
            hostFile_tmp.write(line)
    hostFile.close()
    hostFile_tmp.close()
    os.system('mv '+tmp_filename+' '+filename)

def add_ip(filename,iplist):
    ip_to_add= copy.deepcopy(iplist)
    tmp_filename=os.path.join('/tmp',os.path.basename(filename))
    hostFile = open(filename,"r")
    hostFile_tmp = open(tmp_filename,"w")
    for line in hostFile:
        if line.strip() in iplist:
            ip_to_add.remove(line.strip())
        hostFile_tmp.write(line)
    for ip in ip_to_add:
        hostFile_tmp.write(ip+'\n')
    hostFile.close()
    hostFile_tmp.close()
    os.system('mv '+tmp_filename+' '+filename)

def backup_inventory(inventory):
    dateTimeObj = datetime.now()
    timestampStr = dateTimeObj.strftime("%d-%b-%Y-%H-%M-%S-%f")
    inventory.replace("/",'_')
    backup_ansible_hosts="/tmp/"+inventory.replace("/",'_')+"."+timestampStr
    shutil.copyfile(inventory,backup_ansible_hosts)
    tmp_file_do_not_edit="/tmp/"+inventory.replace("/",'_')+".do_not_edit"
    if os.path.isfile(tmp_file_do_not_edit):
        print("File "+tmp_file_do_not_edit+" exist, it means previous reconfigure had failed. Hence updating inventory to previous state")
        shutil.move(tmp_file_do_not_edit,inventory)

def destroy_unreachable_reconfigure(inventory,nodes_to_remove,playbook): 
    if not os.path.isfile("/etc/ansible/hosts"):
        print("There is no inventory file, are you on the bastion? The cluster has not been resized")
        exit()
    backup_inventory(inventory)
    inventory_dict = parse_inventory(inventory)
    tmp_inventory_destroy="/tmp/"+inventory.replace('/','_')+"_destroy"
    ips_to_remove = []
    for host in nodes_to_remove:
        hostRemoved=False
        for line in inventory_dict['compute_configured']:
            if host in line:
                inventory_dict['compute_configured'].remove(line)
                ips_to_remove.append(line.split("ansible_host=")[1].split("ansible_user=")[0].strip())
                hostRemoved=True
        for line in inventory_dict['compute_to_add']:
            if host in line:
                inventory_dict['compute_to_add'].remove(line)
                ips_to_remove.append(line.split("ansible_host=")[1].split("ansible_user=")[0].strip())
                hostRemoved=True
        for line in inventory_dict['nfs']:
            if host in line:
                inventory_dict['nfs'].remove(line)
    if len(ips_to_remove) != len(nodes_to_remove):
        instances = get_instances(comp_ocid,cn_ocid,CN)
        for instance in instances:
            if instance['display_name'] in nodes_to_remove and not instance['ip'] in ips_to_remove:
                ips_to_remove.append(instance['ip'])
        if len(ips_to_remove) != len(nodes_to_remove):
            print("Some nodes are removed in OCI and removed from the inventory")
            print("Try rerunning with the --nodes option and a list of IPs or Slurm Hostnames to cleanup the bastion")
    write_inventory(inventory_dict,tmp_inventory_destroy)
    if not len(ips_to_remove):
        print("No hostname found, trying anyway with "+" ".join(nodes_to_remove))
        for node in nodes_to_remove: # Temporary fix while the playbook is changed to be able to run multiple at the time
            update_flag = update_cluster(tmp_inventory_destroy,playbook,add_vars={"unreachable_node_list":node})
            time.sleep(10)
    else:
        for ip in ips_to_remove: # Temporary fix while the playbook is changed to be able to run multiple at the time
            update_flag = update_cluster(tmp_inventory_destroy,playbook,add_vars={"unreachable_node_list":ip})
            time.sleep(10)
    if update_flag == 0:
        os.remove(tmp_inventory_destroy)
        inventory_dict['compute_to_destroy']=[]
        tmp_inventory="/tmp/"+inventory.replace('/','_')
        write_inventory(inventory_dict,tmp_inventory)
        os.system('sudo mv '+tmp_inventory+' '+inventory)
        os.system('')
    return update_flag

def destroy_reconfigure(inventory,nodes_to_remove,playbook):
    if not os.path.isfile("/etc/ansible/hosts"):
        print("There is no inventory file, are you on the bastion? The cluster has not been resized")
        exit()
    backup_inventory(inventory)
    inventory_dict = parse_inventory(inventory)
    inventory_dict['compute_to_destroy']=[]
    instances = get_instances(comp_ocid,cn_ocid,CN)
    nodes_to_remove_instances = [{'ip':node,'display_name':node} for node in nodes_to_remove ]
    username="opc"
    for inv_vars in inventory_dict["all:vars"]:
        if inv_vars.startswith("compute_username"):
            username=inv_vars.split("compute_username=")[1].strip()
            break
    if remove_unreachable:
        reachable_instances,unreachable_instances = getreachable(instances,username)
        reachable_node_to_remove,unreachable_node_to_remove = getreachable(nodes_to_remove_instances,username)
    else:
        reachable_instances=instances
        unreachable_instances=[]
        reachable_node_to_remove=nodes_to_remove_instances
        unreachable_node_to_remove=[]
    for host in nodes_to_remove:
        compute_to_remove=[]
        nfs_to_remove=[]
        for line in inventory_dict['compute_configured']:
            if host in line:
                if host in [node['display_name'] for node in reachable_node_to_remove ]:
                    inventory_dict['compute_to_destroy'].append(line)
                compute_to_remove.append(line)
        for line in inventory_dict['compute_to_add']:
            if host in line:
                if host in [node['display_name'] for node in reachable_node_to_remove ]:
                    inventory_dict['compute_to_destroy'].append(line)
                compute_to_remove.append(line)
        for line in inventory_dict['nfs']:
            if host in line:
                if host in [node['display_name'] for node in reachable_node_to_remove ]:
                    nfs_to_remove.append(line)
        for line in compute_to_remove:
            inventory_dict['compute_configured'].remove(line)
        for line in nfs_to_remove:
            inventory_dict['nfs'].remove(line)
    for instance in unreachable_instances:
        for line in inventory_dict['compute_configured']:
            if instance['display_name'] in line:
                inventory_dict['compute_configured'].remove(line)
        for line in inventory_dict['compute_to_add']:
           if instance['display_name'] in line:
                inventory_dict['compute_to_add'].remove(line)
    tmp_inventory_destroy="/tmp/"+inventory.replace('/','_')+"_destroy"
    write_inventory(inventory_dict,tmp_inventory_destroy)
    update_flag = update_cluster(tmp_inventory_destroy,playbook)
    if update_flag == 0:
        os.remove(tmp_inventory_destroy)
        inventory_dict['compute_to_destroy']=[]
        tmp_inventory="/tmp/"+inventory.replace('/','_')
        write_inventory(inventory_dict,tmp_inventory)
        os.system('sudo mv '+tmp_inventory+' '+inventory)
        os.system('')
    return update_flag

def add_reconfigure(comp_ocid,cn_ocid,inventory,CN,specific_hosts=None):
    instances = get_instances(comp_ocid,cn_ocid,CN)
    backup_inventory(inventory)
    inventory_dict = parse_inventory(inventory)
    username="opc"
    for inv_vars in inventory_dict["all:vars"]:
        if inv_vars.startswith("compute_username"):
            username=inv_vars.split("compute_username=")[1].strip()
            break
    reachable_instances=instances
    unreachable_instances=[]
    if not os.path.isfile(inventory):
        print("There is no inventory file, are you on the bastion? The cluster has been resized but not reconfigured")
        exit()
    host_to_wait_for=[]
    for node in reachable_instances:
        name=node['display_name']
        ip=node['ip']
        configured=False
        for line in inventory_dict['compute_configured']:
            if name in line and ip in line:
                configured = True
                break
        if not configured:
            nodeline=name+" ansible_host="+ip+" ansible_user="+username+" role=compute\n"
            if not specific_hosts is None:
                if name in specific_hosts:
                    inventory_dict['compute_to_add'].append(nodeline)
                else:
                    inventory_dict['compute_configured'].append(nodeline)
            else:
                inventory_dict['compute_to_add'].append(nodeline)
            host_to_wait_for.append(ip)
    if len(inventory_dict['nfs'])==0:
        if len(inventory_dict['compute_to_add']) > 0:
            inventory_dict['nfs'].append(inventory_dict['compute_to_add'][0])
        elif len(inventory_dict['compute_configured']) > 0:
            inventory_dict['nfs'].append(inventory_dict['compute_configured'][0])
    hostfile=open("/tmp/hosts_"+cluster_name,'w')
    hostfile.write("\n".join(host_to_wait_for))
    hostfile.close()
    tmp_inventory_add="/tmp/"+inventory.replace('/','_')+"_add"
    write_inventory(inventory_dict,tmp_inventory_add)
    update_flag = update_cluster(tmp_inventory_add,playbooks_dir+"resize_add.yml",hostfile="/tmp/hosts_"+cluster_name)
    if update_flag == 0:
        os.remove(tmp_inventory_add)
        for line in inventory_dict['compute_to_add']:
            inventory_dict['compute_configured'].append(line)
        inventory_dict['compute_to_add']=[]
        tmp_inventory="/tmp/"+inventory.replace('/','_')
        write_inventory(inventory_dict,tmp_inventory)
        os.system('sudo mv '+tmp_inventory+' '+inventory)
    else:
        print("The reconfiguration to add the node(s) had an error")
        print("Try rerunning this command: ansible-playbook -i "+tmp_inventory_add+' '+playbooks_dir+"resize_add.yml" )

def reconfigure(comp_ocid,cn_ocid,inventory,CN, crucial=False):
    instances = get_instances(comp_ocid,cn_ocid,CN)
    if not os.path.isfile(inventory):
        print("There is no inventory file, are you on the bastion? Reconfigure did not happen")
        exit()
    backup_inventory(inventory)
    inventory_dict = parse_inventory(inventory)
    host_to_wait_for=[]
    inventory_dict['compute_configured']=[]
    inventory_dict['compute_to_add']=[]
    username="opc"
    for inv_vars in inventory_dict["all:vars"]:
        if inv_vars.startswith("compute_username"):
            username=inv_vars.split("compute_username=")[1].strip()
            break
    for node in instances:
        name=node['display_name']
        ip=node['ip']
        nodeline=name+" ansible_host="+ip+" ansible_user="+username+" role=compute\n"
        inventory_dict['compute_configured'].append(nodeline)
        host_to_wait_for.append(ip)
    if len(inventory_dict['nfs'])==0:
        if len(inventory_dict['compute_to_add']) > 0:
            inventory_dict['nfs'].append(inventory_dict['compute_to_add'][0])
        elif len(inventory_dict['compute_configured']) > 0:
            inventory_dict['nfs'].append(inventory_dict['compute_configured'][0])
    hostfile=open("/tmp/hosts_"+cluster_name,'w')
    hostfile.write("\n".join(host_to_wait_for))
    hostfile.close()
    tmp_inventory_reconfig="/tmp/"+inventory.replace('/','_')+"_reconfig"
    write_inventory(inventory_dict,tmp_inventory_reconfig)
    if autoscaling:
        playbook=playbooks_dir+"new_nodes.yml"
    else:
        playbook=playbooks_dir+"site.yml"
    if crucial:
        playbook=playbooks_dir+"resize_remove.yml"
    update_flag = update_cluster(tmp_inventory_reconfig,playbook,hostfile="/tmp/hosts_"+cluster_name)
    if update_flag == 0:
        os.system('sudo mv '+tmp_inventory_reconfig+' '+inventory)
    else:
        print("The reconfiguration had an error")
        print("Try rerunning this command: ansible-playbook -i "+tmp_inventory_reconfig+' '+playbook )

def getreachable(instances,username,delay=0):
    if delay == 0 :
        delays=[0]
    else:
        delays=range(0,delay,int(delay/1))#change 1 back to 10
    
    reachable_ips=[]
    for i in delays:
        input_file=open('/tmp/input_hosts_to_check_'+cluster_name,'w')
        for node in instances:
            if not node['ip'] in reachable_ips:
                input_file.write(node['ip']+"\n")
        input_file.close()
        my_env = os.environ.copy()
        my_env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
        p = subprocess.Popen(["/opt/oci-hpc/bin/find_reachable_hosts.sh","/tmp/input_hosts_to_check_"+cluster_name,"/tmp/reachable_hosts_"+cluster_name,username,"0"],env=my_env,stderr = subprocess.PIPE, stdout=subprocess.PIPE)
        while True:
            output = p.stdout.readline().decode()
            if output == '' and p.poll() is not None:
                break
            if output:
                print(output.strip())
        output_file=open('/tmp/reachable_hosts_'+cluster_name,'r')
        for line in output_file:
            reachable_ips.append(line.strip())
        output_file.close()
        if len(instances)==len(reachable_ips):
            break
        if i != delays[-1]:
            time.sleep(int(delay/10))
    reachable_instances=[]
    unreachable_instances=[]
    for ip in reachable_ips:
        added=False
        for node in instances:
            if node['ip']==ip:
                reachable_instances.append(node)
                added=True
    for node in instances:
        if not node in reachable_instances:
            unreachable_instances.append(node)
    return reachable_instances,unreachable_instances

def update_cluster(inventory,playbook,hostfile=None,add_vars={}):
    my_env = os.environ.copy()
    my_env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    rc = 0
    inventory_dict = parse_inventory(inventory)
    username="opc"
    for inv_vars in inventory_dict["all:vars"]:
        if inv_vars.startswith("compute_username"):
            username=inv_vars.split("compute_username=")[1].strip()
            break
    if not hostfile is None:
        p = subprocess.Popen(["/opt/oci-hpc/bin/wait_for_hosts.sh",hostfile,username],env=my_env,stderr = subprocess.PIPE, stdout=subprocess.PIPE)
        while True:
            output = p.stdout.readline().decode()
            if output == '' and p.poll() is not None:
                break
            if output:
                print(output.strip())
        if (rc != 0):
            print("The hosts did not come up for SSH, not reconfiguring")
            return 2
    for add_var in add_vars.keys():
        my_env[add_var] = add_vars[add_var]
    p = subprocess.Popen(["ansible-playbook","-i",inventory,playbook],env=my_env,stderr = subprocess.PIPE, stdout=subprocess.PIPE)
    while True:
        output = p.stdout.readline().decode()
        if output == '' and p.poll() is not None:
            break
        if output:
            print(output.strip())
    rc = p.returncode
    tmp_file_do_not_edit="/tmp/"+inventory.replace("/",'_')+".do_not_edit"
    if (rc == 0):
        print("success")
        if os.path.isfile(tmp_file_do_not_edit):
            os.remove(tmp_file_do_not_edit)
        return 0
    else:
        print("return code from ansible playbook job was non-zero, review what failed during ansible tasks run : "+str(rc))
        if os.path.isfile(tmp_file_do_not_edit):
            shutil.move(tmp_file_do_not_edit, "/tmp/etc_ansible_hosts.do_not_edit.old")
        print("Resolve the issue which caused ansible playbook to fail (hint: look for word fatal in above output). Then run the below command to only run the reconfigure step (ansible playbook) without again adding or removing node from HPC/GPU cluster.")
        return 1
        #if mode == 'add':
        #    print("Command:  python3 playbooks/resize.py reconfigure --nodes newly_added_node1_hostname newly_added_node2_hostname ")
        #if mode == 'remove':
        #    print("Command:  python3 playbooks/resize.py reconfigure --slurm_only_update true ")

def getNFSnode(inventory):
    dict = parse_inventory(inventory)
    if dict is None:
        return ''
    if len(dict['nfs']) == 0:
        return ''
    return dict['nfs'][0].split()[0]

def get_summary(comp_ocid,cluster_name):
    CN = True
    cn_summaries = computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data
    running_clusters = 0
    scaling_clusters = 0
    cn_summary=None
    for cn_summary_tmp in cn_summaries:
        if cn_summary_tmp.lifecycle_state == "RUNNING":
            cn_summary = cn_summary_tmp
            running_clusters = running_clusters + 1
        elif cn_summary_tmp.lifecycle_state == "SCALING":
            scaling_clusters = scaling_clusters + 1
    if running_clusters == 0:
        cn_summaries = computeManagementClient.list_instance_pools(comp_ocid,display_name=cluster_name).data
        if len(cn_summaries) > 0:
            CN = False
            for cn_summary_tmp in cn_summaries:
                if cn_summary_tmp.lifecycle_state == "RUNNING":
                    cn_summary = cn_summary_tmp
                    running_clusters = running_clusters + 1 
                elif cn_summary_tmp.lifecycle_state == "SCALING":
                    scaling_clusters = scaling_clusters + 1
        if running_clusters == 0:
            if scaling_clusters:
                print("No running cluster was found but there is a cluster in SCALING mode, try rerunning in a moment")
            else:
                print("The cluster was not found")
            return None,None,True
    if running_clusters > 1:
        print("There were multiple running clusters with this name, we selected the one with OCID:"+cn_summary.id)
    if CN:
        ip_summary=cn_summary.instance_pools[0]
    else:
        ip_summary=cn_summary
    return cn_summary,ip_summary,CN

def updateTFState(inventory,cluster_name,size):
    try:
        TFStateName = os.path.join(os.path.dirname(inventory),'terraform.tfstate')
        if not os.path.isfile(TFStateName) or inventory == "/etc/ansible/hosts":
            return 0
        tmpTFStateName = '/tmp/'+cluster_name+'.tfstate'
        TFState=open(TFStateName,'r')
        tmpTFState=open(tmpTFStateName,'w')
        for line in TFState:
            if line.strip().startswith('"serial":'):
                serial=int(line.strip().split('"serial":')[1].split(',')[0])
                tmpTFState.write(line.replace(str(serial),str(serial+1)))
            elif line.strip().startswith('"size":'):
                currentsize=int(line.strip().split('"size":')[1].split(',')[0])
                tmpTFState.write(line.replace(str(currentsize),str(size)))
            else:
                tmpTFState.write(line)
        tmpTFState.close()
        TFState.close()

        TFvarName = os.path.join(os.path.dirname(inventory),'variables.tf')
        if not os.path.isfile(TFStateName) or inventory == "/etc/ansible/hosts":
            return 0
        tmpTFVarName = '/tmp/'+cluster_name+'_variables.tf'
        TFVar=open(TFvarName,'r')
        tmpTFVar=open(tmpTFVarName,'w')
        for line in TFVar:
            if line.strip().startswith('variable "node_count"'):
                currentsize=int(line.strip().split('default="')[1].split('"')[0])
                tmpTFVar.write(line.replace(str(currentsize),str(size)))
            else:
                tmpTFVar.write(line)
        tmpTFVar.close()
        TFVar.close()
        os.system("cd "+os.path.dirname(inventory)+";terraform state push "+tmpTFStateName)
        os.system("mv "+tmpTFVarName+" "+TFvarName)
        return 1
    except:
        return 0
    

batchsize=12
inventory="/etc/ansible/hosts"
playbooks_dir="/opt/oci-hpc/playbooks/"

parser = argparse.ArgumentParser(description='Script to resize the CN')
parser.add_argument('--compartment_ocid', help='OCID of the compartment, defaults to the Compartment OCID of the localhost')
parser.add_argument('--cluster_name', help='Name of the cluster to resize. Defaults to the name included in the bastion')
parser.add_argument('mode', help='Mode type. add/remove node options, implicitly configures newly added nodes. Also implicitly reconfigure/restart services like Slurm to recognize new nodes. Similarly for remove option, terminates nodes and implicitly reconfigure/restart services like Slurm on rest of the cluster nodes to remove reference to deleted nodes.',choices=['add','remove','remove_unreachable','list','reconfigure'],default='list',nargs='?')
parser.add_argument('number', type=int, help="Number of nodes to add or delete if a list of hostnames is not defined",nargs='?')
parser.add_argument('--nodes', help="List of nodes to delete (Space Separated)",nargs='+')
parser.add_argument('--no_reconfigure', help='If present. Does not rerun the playbooks',action='store_true',default=False)
parser.add_argument('--user_logging', help='If present. Use the default settings in ~/.oci/config to connect to the API. Default is using instance_principal',action='store_true',default=False)
parser.add_argument('--force', help='If present. Nodes will be removed even if the destroy playbook failed',action='store_true',default=False)
parser.add_argument('--ansible_crucial', help='If present during reconfiguration, only crucial ansible playbooks will be executed on the live nodes. Non live nodes will be removed',action='store_true',default=False)
parser.add_argument('--remove_unreachable', help='If present, nodes that are not sshable will be terminated before running the action that was requested (Example Adding a node) ',action='store_true',default=False)

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

if cluster_name == metadata['displayName'].replace('-bastion',''):
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

hostnames=args.nodes
if hostnames is None:
    hostnames=[]

if args.mode=='remove' and args.number is None and args.nodes is None:
    print("STDOUT: No Nodes to remove")
    exit()

if args.mode=='add' and args.number is None:
    print("STDOUT: No Nodes to add")
    exit()

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

if user_logging:
    config_oci = oci.config.from_file()
    computeClient = oci.core.ComputeClient(config_oci)
    computeManagementClient = oci.core.ComputeManagementClient(config_oci)
    ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(computeManagementClient)
    virtualNetworkClient = oci.core.VirtualNetworkClient(config_oci)
else:
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    computeClient = oci.core.ComputeClient(config={}, signer=signer)
    computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=signer)
    ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(computeManagementClient)
    virtualNetworkClient = oci.core.VirtualNetworkClient(config={}, signer=signer)

cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
if cn_summary is None:
    exit()
cn_ocid =cn_summary.id
current_size=ip_summary.size
if CN:
    ipa_ocid = cn_summary.instance_pools[0].id
else:
    ipa_ocid = cn_ocid

if args.mode == 'list':
    state = cn_summary.lifecycle_state
    print("Cluster is in state:"+state )
    cn_instances = get_instances(comp_ocid,cn_ocid,CN)
    for cn_instance in cn_instances:
        print(cn_instance['display_name']+' '+cn_instance['ip']+' '+cn_instance['ocid'])
elif args.mode == 'reconfigure':
    if len(hostnames)>0:
        add_reconfigure(comp_ocid,cn_ocid,inventory,CN,specific_hosts=hostnames)
    else:
        reconfigure(comp_ocid,cn_ocid,inventory,CN,crucial=ansible_crucial)

else:
    wait_for_running_status(cluster_name,comp_ocid,cn_ocid,CN)
    cn_instances = get_instances(comp_ocid,cn_ocid,CN)
    inventory_instances =[]
    only_inventory_instance=[]
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
            reachable_instances,unreachable_instances=getreachable(cn_instances+only_inventory_instance,username,delay=10)
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
            reachable_instances,unreachable_instances=getreachable(inventory_instances_to_test,username,delay=10)
            hostnames_to_remove=hostnames
            if len(unreachable_instances):
                print("STDOUT: At least one unreachable node is in the inventory and was not mentionned with OCI hostname to be removed. Trying anyway")
    else:
        reachable_instances,unreachable_instances=getreachable(inventory_instances,username,delay=10)
        if len(unreachable_instances):
            if not remove_unreachable:
                print("STDOUT: At least one unreachable node is in the inventory")
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
    hostnames_to_remove_len=len(hostnames_to_remove)
    if hostnames_to_remove_len:
        if not no_reconfigure:
            playbook = playbooks_dir+"resize_remove_unreachable.yml"
            error_code = destroy_unreachable_reconfigure(inventory,hostnames_to_remove,playbook)
            if error_code != 0:
                print("STDOUT: The nodes could not be removed. Try running this with Force")
                if not force:
                    exit(1)
                else:
                    print("STDOUT: Force deleting the nodes")
        while len(hostnames_to_remove) > 0:
            terminated_instances=0
            if len(hostnames_to_remove) >batchsize:
                batch = hostnames_to_remove[:batchsize]
            else:
                batch = hostnames_to_remove
            cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
            current_size = ip_summary.size
            for instanceName in batch:
                try:
                    instance_id = computeClient.list_instances(comp_ocid,display_name=instanceName).data[0].id
                    instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=instance_id,is_auto_terminate=True,is_decrement_size=True)
                    print("STDOUT: The instance "+instanceName+" is terminating")
                    ComputeManagementClientCompositeOperations.detach_instance_pool_instance_and_wait_for_work_request(ipa_ocid,instance_details)
                    terminated_instances = terminated_instances + 1
                except:
                    print("The instance "+instanceName+" does not exist")
            hostnames_to_remove=hostnames_to_remove[batchsize:]
        cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
        newsize=ip_summary.size
        updateTFState(inventory,cluster_name,newsize)
        print("STDOUT: Resized to "+str(newsize)+" instances")
        if error_code != 0 and force:
            print("STDOUT: The nodes were forced deleted, trying to reconfigure the left over nodes")
            reconfigure(comp_ocid,cn_ocid,inventory,CN)

    if args.mode == 'add':
        size = current_size - hostnames_to_remove_len + args.number
        update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
        ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(ipa_ocid,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
        updateTFState(inventory,cluster_name,size)
        if not no_reconfigure:
            add_reconfigure(comp_ocid,cn_ocid,inventory,CN)