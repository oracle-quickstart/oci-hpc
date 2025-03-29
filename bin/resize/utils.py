import oci
import time
import subprocess
import requests
import shutil
import os
import copy
import ipaddress
from datetime import datetime
from ociobj import ocicore, ocicluster

def get_metadata():
    """ Make a request to metadata endpoint """
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()

def wait_for_running_status(ocicluster,ocicore,expected_size=None):
    while True:
        if ocicluster.CN == "CC": 
            break
        elif ocicluster.CN == "CN":
            state = ocicore.computeManagementClient.get_cluster_network(ocicluster.cn_ocid).data.lifecycle_state
            instances=ocicore.computeManagementClient.list_cluster_network_instances(ocicluster.comp_ocid,ocicluster.cn_ocid).data
        else:
            state = ocicore.computeManagementClient.get_instance_pool(ocicluster.cn_ocid).data.lifecycle_state
            instances=ocicore.computeManagementClient.list_instance_pool_instances(ocicluster.comp_ocid,ocicluster.cn_ocid).data
        if state != 'RUNNING':
            print("Cluster state is "+state+", cannot add or remove nodes")
            print("Waiting...")
            time.sleep(30)
        elif not expected_size is None:
            if expected_size == len(instances):
                break
            else:
                print("STDOUT: The instance list does not match the expected size")
                time.sleep(30)
        else:
            break
    return True

def get_instances(ocicluster,ocicore):
    cn_instances=[]
    if ocicluster.CN == "CC":
        instances = ocicore.computeClient.list_instances(ocicluster.comp_ocid,compute_cluster_id=ocicluster.cn_ocid).data
        for instance in instances:
            if instance.lifecycle_state == "TERMINATED":
                continue
            try:
                for potential_vnic_attachment in oci.pagination.list_call_get_all_results(ocicore.computeClient.list_vnic_attachments,compartment_id=ocicluster.comp_ocid,instance_id=instance.id).data:
                    if potential_vnic_attachment.display_name is None:
                        vnic_attachment = potential_vnic_attachment
                vnic = ocicore.virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
            except:
                continue
            cn_instances.append({'display_name':instance.display_name,'ip':vnic.private_ip,'ocid':instance.id})
    else:
        if ocicluster.CN == "CN":
            instance_summaries = oci.pagination.list_call_get_all_results(ocicore.computeManagementClient.list_cluster_network_instances,ocicluster.comp_ocid,ocicluster.cn_ocid).data
        else:
            instance_summaries = oci.pagination.list_call_get_all_results(ocicore.computeManagementClient.list_instance_pool_instances,ocicluster.comp_ocid,ocicluster.cn_ocid).data
        for instance_summary in instance_summaries:
            try:
                instance = ocicore.computeClient.get_instance(instance_summary.id).data
                for potential_vnic_attachment in oci.pagination.list_call_get_all_results(ocicore.computeClient.list_vnic_attachments,compartment_id=ocicluster.comp_ocid,instance_id=instance.id).data:
                    if potential_vnic_attachment.display_name is None:
                        vnic_attachment = potential_vnic_attachment
                vnic = ocicore.virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
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

def getNFSnode(inventory):
    dict = parse_inventory(inventory)
    if dict is None:
        return ''
    if len(dict['nfs']) == 0:
        return ''
    if dict['nfs'][0] == '\n':
        return ''
    else:
        return dict['nfs'][0].split()[0]

def get_summary(comp_ocid,cluster_name,ocicore):
    CN = "CN"
    cn_summaries = ocicore.computeManagementClient.list_cluster_networks(comp_ocid,display_name=cluster_name).data
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
        try:
            cn_summaries = ocicore.computeClient.list_compute_clusters(comp_ocid,display_name=cluster_name).data.items
        except:
            print("The list_compute_clusters call returned an error, considering no Compute CLusters are present")
            cn_summaries = []
        if len(cn_summaries) > 0:
            CN = "CC"
            for cn_summary_tmp in cn_summaries:
                if cn_summary_tmp.lifecycle_state == "ACTIVE" and cn_summary_tmp.display_name == cluster_name :
                    cn_summary = cn_summary_tmp
                    running_clusters = running_clusters + 1
        if running_clusters == 0:
            cn_summaries = ocicore.computeManagementClient.list_instance_pools(comp_ocid,display_name=cluster_name).data
            if len(cn_summaries) > 0:
                CN = "IP"
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
    if CN == "CN":
        ip_summary=cn_summary.instance_pools[0]
    elif CN == "CC":
        ip_summary=None
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
    
def getLaunchInstanceDetails(instance,comp_ocid,cn_ocid,max_previous_index,index,ocicore):

    agent_config=instance.agent_config
    agent_config.__class__ = oci.core.models.LaunchInstanceAgentConfigDetails

    for potential_vnic_attachment in oci.pagination.list_call_get_all_results(ocicore.computeClient.list_vnic_attachments,compartment_id=comp_ocid,instance_id=instance.id).data:
        if potential_vnic_attachment.display_name is None:
            vnic_attachment = potential_vnic_attachment
    splitted_name=instance.display_name.split('-')
    create_vnic_details=oci.core.models.CreateVnicDetails(assign_public_ip=False,subnet_id=vnic_attachment.subnet_id)

    shape_config=instance.shape_config
    try:
        nvmes=shape_config.local_disks
        launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,nvmes=nvmes,ocpus=shape_config.ocpus)
    except:
        launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,ocpus=shape_config.ocpus)

    splitted_name[-1]=str(max_previous_index+1+index)
    new_display_name = '-'.join(splitted_name)
    launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=instance.availability_domain, compartment_id=comp_ocid,compute_cluster_id=cn_ocid,shape=instance.shape,shape_config=launchInstanceShapeConfigDetails,source_details=instance.source_details,metadata=instance.metadata,display_name=new_display_name,freeform_tags=instance.freeform_tags,create_vnic_details=create_vnic_details)
    return launch_instance_details

def getreachable(instances,ocicluster,delay=0):
    if delay == 0 :
        delays=[0]
    else:
        delays=range(0,delay,int(delay/1))#change 1 back to 10
    
    reachable_ips=[]
    for i in delays:
        input_file=open('/tmp/input_hosts_to_check_'+ocicluster.cluster_name,'w')
        for node in instances:
            if not node['ip'] in reachable_ips:
                input_file.write(node['ip']+"\n")
        input_file.close()
        my_env = os.environ.copy()
        my_env["ANSIBLE_HOST_KEY_CHECKING"] = "False"
        p = subprocess.Popen(["/opt/oci-hpc/bin/find_reachable_hosts.sh","/tmp/input_hosts_to_check_"+ocicluster.cluster_name,"/tmp/reachable_hosts_"+ocicluster.cluster_name,ocicluster.username,"0"],env=my_env,stderr = subprocess.PIPE, stdout=subprocess.PIPE)
        while True:
            output = p.stdout.readline().decode()
            if output == '' and p.poll() is not None:
                break
            if output:
                print(output.strip())
        output_file=open('/tmp/reachable_hosts_'+ocicluster.cluster_name,'r')
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

def get_instancename(host_file):
    """
    Parse a host file and returns dictionary with slurm host name as key and oci instance name as value
    Args:
        host_file: Path to the host file.
    Returns:
        Returns dictionary with slurm host name as key and oci instance name as value
        Returns empty dictionary when host file does not exist or no matching records found in host file.
    """
    try:
        host = open(host_file, "r")
    except:
        return None
    hostnamemap = {}
    for line in host:
        parts = line.split()
        if len(parts) >= 4:  # check if the line has atleast 4 values - ipaddress hostname hostnamelocalvcn instancename
            hostname = parts[1]
            hostnamelocalvcn = parts[2]
            instancename = parts[3]            
            if hostnamelocalvcn.endswith(".local.vcn"): 
                hostnamemap[hostname] = instancename
    host.close()
    return hostnamemap

def check_replace_slumhostname(hostnames, cn_instances, ocicluster):
    hostnames_updated = []
    hostinstancenamemap = get_instancename(ocicluster.hostfile)
    cn_instancenames = []
    for instance in cn_instances:
        cn_instancenames.append(instance['display_name'])
    for hostname in hostnames:
        if hostname not in cn_instancenames:
            if hostname.startswith(ocicluster.hostname_convention) and hostname in hostinstancenamemap:
                print(f"STDOUT: Using the instance name {hostinstancenamemap[hostname]} for the node {hostname}")
                hostname = hostinstancenamemap[hostname]                
            else:
                print(f"ERROR: Node {hostname} does not appear to exist in this cluster. Please check your arguments and rerun")
        hostnames_updated.append(hostname)
    return hostnames_updated        