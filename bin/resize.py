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
            vnic_attachment = oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=comp_ocid,instance_id=instance.id).data[0]
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

def destroy_reconfigure(inventory,nodes_to_remove,playbook):
    if not os.path.isfile("/etc/ansible/hosts"):
        print("There is no inventory file, are you on the bastion? The cluster has not been resized")
        exit()
    backup_inventory(inventory)
    inventory_dict = parse_inventory(inventory)
    inventory_dict['compute_to_destroy']=[]
    for host in nodes_to_remove:
        compute_to_remove=[]
        nfs_to_remove=[]
        for line in inventory_dict['compute_configured']:
            if host in line:
                inventory_dict['compute_to_destroy'].append(line)
                compute_to_remove.append(line)
        for line in inventory_dict['compute_to_add']:
            if host in line:
                inventory_dict['compute_to_destroy'].append(line)
                compute_to_remove.append(line)
        for line in inventory_dict['nfs']:
            if host in line:
                nfs_to_remove.append(line)
        for line in compute_to_remove:
            inventory_dict['compute_configured'].remove(line)
        for line in nfs_to_remove:
            inventory_dict['nfs'].remove(line)
    tmp_inventory_destroy="/tmp/"+inventory.replace('/','_')+"_destroy"
    write_inventory(inventory_dict,tmp_inventory_destroy)
    update_flag = update_cluster(tmp_inventory_destroy,playbook)
    if update_flag == 0:
        os.remove(tmp_inventory_destroy)
        inventory_dict['compute_to_destroy']=[]
        tmp_inventory="/tmp/"+inventory.replace('/','_')
        write_inventory(inventory_dict,tmp_inventory)
        os.system('sudo mv '+tmp_inventory+' '+inventory)
    return update_flag

def add_reconfigure(comp_ocid,cn_ocid,inventory,CN,specific_hosts=None):
    instances = get_instances(comp_ocid,cn_ocid,CN)
    if not os.path.isfile(inventory):
        print("There is no inventory file, are you on the bastion? The cluster has been resized but not reconfigured")
        exit()
    backup_inventory(inventory)
    inventory_dict = parse_inventory(inventory)
    host_to_wait_for=[]
    for node in instances:
        name=node['display_name']
        ip=node['ip']
        configured=False
        for line in inventory_dict['compute_configured']:
            if name in line and ip in line:
                configured = True
                break
        if not configured:
            nodeline=name+" ansible_host="+ip+" ansible_user=opc role=compute\n"
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
    hostfile=open("/tmp/hosts",'w')
    hostfile.write("\n".join(host_to_wait_for))
    hostfile.close()
    tmp_inventory_add="/tmp/"+inventory.replace('/','_')+"_add"
    write_inventory(inventory_dict,tmp_inventory_add)
    update_flag = update_cluster(tmp_inventory_add,playbooks_dir+"resize_add.yml",hostfile="/tmp/hosts")
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
    if remove_unreachable:
        reachable_instances= getreachable(instances)
    else:
        reachable_instances=instances
    for node in reachable_instances:
        name=node['display_name']
        ip=node['ip']
        nodeline=name+" ansible_host="+ip+" ansible_user=opc role=compute\n"
        inventory_dict['compute_configured'].append(nodeline)
        host_to_wait_for.append(ip)
    if len(inventory_dict['nfs'])==0:
        if len(inventory_dict['compute_to_add']) > 0:
            inventory_dict['nfs'].append(inventory_dict['compute_to_add'][0])
        elif len(inventory_dict['compute_configured']) > 0:
            inventory_dict['nfs'].append(inventory_dict['compute_configured'][0])
    hostfile=open("/tmp/hosts",'w')
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
    update_flag = update_cluster(tmp_inventory_reconfig,playbook,hostfile="/tmp/hosts")
    if update_flag == 0:
        os.system('sudo mv '+tmp_inventory_reconfig+' '+inventory)
    else:
        print("The reconfiguration had an error")
        print("Try rerunning this command: ansible-playbook -i "+tmp_inventory_reconfig+' '+playbook )

def getreachable(instances):
    input_file=open('/tmp/input_hosts_to_check','w')
    for node in instances:
        input_file.write(node['ip']+"\n")
    input_file.close()
    print("/opt/oci-hpc/bin/find_reachable_hosts.sh /tmp/input_hosts_to_check /tmp/reachable_hosts")
    my_env = os.environ.copy()
    my_env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    p = subprocess.Popen(["/opt/oci-hpc/bin/find_reachable_hosts.sh","/tmp/input_hosts_to_check","/tmp/reachable_hosts"],env=my_env,stderr = subprocess.PIPE, stdout=subprocess.PIPE)
    while True:
        output = p.stdout.readline().decode()
        if output == '' and p.poll() is not None:
            break
        if output:
            print(output.strip())

    output_file=open('/tmp/reachable_hosts','r')
    reachable_ips=[]
    reachable_instances=[]
    for line in output_file:
        reachable_ips.append(line.strip())
    output_file.close()
    for ip in reachable_ips:
        for node in instances:
            if node['ip']==ip:
                reachable_instances.append(node)
    return reachable_instances

def update_cluster(inventory,playbook,hostfile=None):
    my_env = os.environ.copy()
    my_env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
    rc = 0
    if not hostfile is None:
        p = subprocess.Popen(["/opt/oci-hpc/bin/wait_for_hosts.sh",hostfile],env=my_env,stderr = subprocess.PIPE, stdout=subprocess.PIPE)
        while True:
            output = p.stdout.readline().decode()
            if output == '' and p.poll() is not None:
                break
            if output:
                print(output.strip())
        if (rc != 0):
            print("The hosts did not come up for SSH, not reconfiguring")
            return 2

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
    return dict['nfs'][0].split()[0]

def get_summary(comp_ocid,cluster_name):
    CN = True
    cn_summaries = computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data
    running_clusters = 0
    cn_summary=None
    for cn_summary_tmp in cn_summaries:
        if cn_summary_tmp.lifecycle_state == "RUNNING":
            cn_summary = cn_summary_tmp
            running_clusters = running_clusters + 1
    if running_clusters == 0:
        cn_summaries = computeManagementClient.list_instance_pools(comp_ocid,display_name=cluster_name).data
        if len(cn_summaries) > 0:
            CN = False
            for cn_summary_tmp in cn_summaries:
                if cn_summary_tmp.lifecycle_state == "RUNNING":
                    cn_summary = cn_summary_tmp
                    running_clusters = running_clusters + 1
        if running_clusters == 0:
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
        os.system("cd "+os.path.dirname(inventory)+";terraform state push "+tmpTFStateName)
        return 1
    except:
        return 0
    

batchsize=12
inventory="/etc/ansible/hosts"
playbooks_dir="/opt/oci-hpc/playbooks/"

parser = argparse.ArgumentParser(description='Script to resize the CN')
parser.add_argument('--compartment_ocid', help='OCID of the compartment, defaults to the Compartment OCID of the localhost')
parser.add_argument('--cluster_name', help='Name of the cluster to resize. Defaults to the name included in the bastion')
parser.add_argument('mode', help='Mode type. add/remove node options, implicitly configures newly added nodes. Also implicitly reconfigure/restart services like Slurm to recognize new nodes. Similarly for remove option, terminates nodes and implicitly reconfigure/restart services like Slurm on rest of the cluster nodes to remove reference to deleted nodes.',choices=['add','remove','list','reconfigure'],default='list',nargs='?')
parser.add_argument('number', type=int, help="Number of nodes to add or delete if a list of hostnames is not defined",nargs='?')
parser.add_argument('--nodes', help="List of nodes to delete",nargs='+')
parser.add_argument('--no_reconfigure', help='If present. Does not rerun the playbooks',action='store_true',default=False)
parser.add_argument('--user_logging', help='If present. Use the default settings in ~/.oci/config to connect to the API. Default is using instance_principal',action='store_true',default=False)
parser.add_argument('--force', help='If present. Nodes will be removed even if the destroy playbook failed',action='store_true',default=False)
parser.add_argument('--ansible_crucial', help='If present during reconfiguration, only crucial ansible playbooks will be executed on the live nodes. Non live nodes will be removed',action='store_true',default=False)
parser.add_argument('--remove_unreachable', help='If present, nodes that are not sshable will be removed from the config',action='store_true',default=False)

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
    autoscaling=False
else:
    inventory= "/opt/oci-hpc/autoscaling/clusters/"+cluster_name+'/inventory'
    autoscaling = True

hostnames=args.nodes
if hostnames is None:
    hostnames=[]

if args.mode=='remove' and args.number is None and args.nodes is None:
    print("No Nodes to remove")
    exit()

if args.mode=='add' and args.number is None:
    print("No Nodes to add")
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
    force=args.user_logging

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
    if args.mode == 'add':
        size = current_size + args.number
        update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
        ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(ipa_ocid,update_size,['RUNNING'])
        updateTFState(inventory,cluster_name,size)
        if not no_reconfigure:
            add_reconfigure(comp_ocid,cn_ocid,inventory,CN)
    elif args.mode == 'remove':
        if len(hostnames) == 0:
            cn_instances = get_instances(comp_ocid,cn_ocid,CN)
            nfsNode=getNFSnode(inventory)
            non_nfs=[i for i in cn_instances if i['display_name'] != nfsNode]
            if args.number < len(cn_instances):
                hostnames=[non_nfs[i]['display_name'] for i in range(len(non_nfs)-args.number,len(non_nfs))]
            else:
                hostnames=[cn_instances[i]['display_name'] for i in range(len(cn_instances))]
        if not no_reconfigure:
            playbook = playbooks_dir+"resize_remove.yml"
            error_code = destroy_reconfigure(inventory,hostnames,playbook)
            if error_code != 0:
                print("The nodes could not be removed. Try running this with Force")
                if not force:
                    exit()
                else:
                    print("Force deleting the nodes")

        while len(hostnames) > 0:
            terminated_instances=0
            if len(hostnames) >batchsize:
                batch = hostnames[:batchsize]
            else:
                batch = hostnames
            cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
            current_size = ip_summary.size
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
        cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
        newsize=ip_summary.size
        updateTFState(inventory,cluster_name,newsize)
        print("Resized to "+str(newsize)+" instances")
        if error_code != 0 and force:
            print("The nodes were forced deleted, trying to reconfigure the left over nodes")
            reconfigure(comp_ocid,cn_ocid,inventory,CN)
