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

def get_metadata():
    """ Make a request to metadata endpoint """
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()

def wait_for_running_status(cluster_name,comp_ocid,cn_ocid,CN,expected_size=None):
    while True:
        if CN == "CC": 
            break
        elif CN == "CN":
            state = computeManagementClient.get_cluster_network(cn_ocid).data.lifecycle_state
            instances=computeManagementClient.list_cluster_network_instances(comp_ocid,cn_ocid).data
        else:
            state = computeManagementClient.get_instance_pool(cn_ocid).data.lifecycle_state
            instances=computeManagementClient.list_instance_pool_instances(comp_ocid,cn_ocid).data
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

def get_instances(comp_ocid,cn_ocid,CN):
    cn_instances=[]
    if CN == "CC":
        instances = computeClient.list_instances(comp_ocid,compute_cluster_id=cn_ocid).data
        for instance in instances:
            if instance.lifecycle_state == "TERMINATED":
                continue
            try:
                for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=comp_ocid,instance_id=instance.id).data:
                    if potential_vnic_attachment.display_name is None:
                        vnic_attachment = potential_vnic_attachment
                vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
            except:
                continue
            cn_instances.append({'display_name':instance.display_name,'ip':vnic.private_ip,'ocid':instance.id})
    else:
        if CN == "CN":
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

def get_summary(comp_ocid,cluster_name):
    CN = "CN"
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
        try:
            cn_summaries = computeClient.list_compute_clusters(comp_ocid,display_name=cluster_name).data.items
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
            cn_summaries = computeManagementClient.list_instance_pools(comp_ocid,display_name=cluster_name).data
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
    
def getLaunchInstanceDetails(instance,comp_ocid,cn_ocid,max_previous_index,index):

    agent_config=instance.agent_config
    agent_config.__class__ = oci.core.models.LaunchInstanceAgentConfigDetails

    for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=comp_ocid,instance_id=instance.id).data:
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

def mongo_remove(hostnames):
    try:
        command = "mongosh "+db_name+" --quiet --eval 'db."+collection_name+".updateMany({ hostname: { $in: ["+','.join(hostnames)+"] } },{ $set: { status: \"to_terminate\",terminated:"+current_time_str+" } });'"
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return result.stdout
    except Exception as e:
        print(f"Error running mongosh: {e}")
        sys.exit(1)

def restart_node_updater():
    try:
        command = "sudo systemctl start node_updater.service"
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return result.stdout
    except Exception as e:
        print(f"Error running mongosh: {e}")
        sys.exit(1)
   
batchsize=12
inventory="/etc/ansible/hosts"
playbooks_dir="/opt/oci-hpc/playbooks/"

parser = argparse.ArgumentParser(description='Script to resize the CN')
parser.add_argument('--compartment_ocid', help='OCID of the compartment, defaults to the Compartment OCID of the localhost')
parser.add_argument('--cluster_name', help='Name of the cluster to resize. Defaults to the name included in the controller')
parser.add_argument('mode', help='Mode type. add/remove node options, implicitly configures newly added nodes. Also implicitly reconfigure/restart services like Slurm to recognize new nodes. Similarly for remove option, terminates nodes and implicitly reconfigure/restart services like Slurm on rest of the cluster nodes to remove reference to deleted nodes.',choices=['add','remove','list'],default='list',nargs='?')
parser.add_argument('number', type=int, help="Number of nodes to add or delete if a list of hostnames is not defined",nargs='?')
parser.add_argument('--nodes', help="List of nodes to delete (Space Separated)",nargs='+')
parser.add_argument('--user_logging', help='If present. Use the default settings in ~/.oci/config to connect to the API. Default is using instance_principal',action='store_true',default=False)

args = parser.parse_args()


# Get the current date and time with milliseconds
current_time = datetime.now()
current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
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
db_name=None
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("db_name"):
        db_name=inv_vars.split("db_name=")[1].strip()
        break
collection_name=None
for inv_vars in inventory_dict["all:vars"]:
    if inv_vars.startswith("collection_name"):
        collection_name=inv_vars.split("collection_name=")[1].strip()
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

if args.user_logging is None:
    user_logging=False
else:
    user_logging=args.user_logging

if user_logging:
    config_oci = oci.config.from_file()
    computeClient = oci.core.ComputeClient(config_oci)
    ComputeClientCompositeOperations = oci.core.ComputeClientCompositeOperations(computeClient)
    computeManagementClient = oci.core.ComputeManagementClient(config_oci)
    ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(computeManagementClient)
    virtualNetworkClient = oci.core.VirtualNetworkClient(config_oci)
    dns_client = oci.dns.DnsClient(config_oci)
else:
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    computeClient = oci.core.ComputeClient(config={}, signer=signer)
    ComputeClientCompositeOperations= oci.core.ComputeClientCompositeOperations(computeClient)
    computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=signer)
    ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(computeManagementClient)
    virtualNetworkClient = oci.core.VirtualNetworkClient(config={}, signer=signer)
    dns_client = oci.dns.DnsClient(config={}, signer=signer)

cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
if cn_summary is None:
    exit(1)
cn_ocid =cn_summary.id

if CN != "CC":
    current_size=ip_summary.size
    if CN == "CN":
        ipa_ocid = cn_summary.instance_pools[0].id
    else:
        ipa_ocid = cn_ocid

if args.mode == 'list':
    state = cn_summary.lifecycle_state
    print("Cluster is in state:"+state )
    cn_instances = get_instances(comp_ocid,cn_ocid,CN)
    for cn_instance in cn_instances:
        print(cn_instance['display_name']+' '+cn_instance['ip']+' '+cn_instance['ocid'])

else:
    wait_for_running_status(cluster_name,comp_ocid,cn_ocid,CN)
    cn_instances = get_instances(comp_ocid,cn_ocid,CN)
    inventory_instances =[]
    only_inventory_instance=[]
    if args.mode == 'remove':
        if len(hostnames) == 0:
            hostnames=[i['display_name'] for i in cn_instances[-args.number:]]
        hostnames_to_remove_len=len(hostnames)
        hostnames_removed=copy.deepcopy(hostnames)
        if hostnames_to_remove_len:
            terminated_instances=0
            cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
            if CN != "CC":
                current_size = ip_summary.size
            for instanceName in hostnames:
                try:
                    instance_id = computeClient.list_instances(comp_ocid,display_name=instanceName).data[0].id
                    if CN == "CC":
                        ComputeClientCompositeOperations.terminate_instance_and_wait_for_state(instance_id,wait_for_states=["TERMINATING","TERMINATED"])
                    else:
                        instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=instance_id,is_auto_terminate=True,is_decrement_size=True)
                        ComputeManagementClientCompositeOperations.detach_instance_pool_instance_and_wait_for_work_request(ipa_ocid,instance_details)
                    terminated_instances = terminated_instances + 1
                    print("STDOUT: The instance "+instanceName+" is terminating")
                except:
                    hostnames_removed.remove(instanceName)
                    print("STDOUT: The instance "+instanceName+" does not exist")
            cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
            if CN == "CC":
                instance_id = computeClient.list_instances(comp_ocid,display_name=hostnames_to_remove[-1]).data[0].id
                for i in range(10):
                    try:
                        instance_state = computeClient.get_instance(instance_id).data.lifecycle_state
                        if instance_state == "TERMINATED":
                            break
                        else:
                            time.sleep(10)
                    except:
                        hostnames_removed.remove(hostnames_to_remove[-1])
                        break
                cn_instances = get_instances(comp_ocid,cn_ocid,CN)
                newsize=len(cn_instances)
            else:
                newsize=ip_summary.size
                updateTFState(inventory,cluster_name,newsize)
            mongo_remove(hostnames_removed)
            restart_node_updater()
            print("STDOUT: Resized to "+str(newsize)+" instances")
            # Run Nmap scan to find open HTTP servers

    if args.mode == 'add':
        cn_instances = get_instances(comp_ocid,cn_ocid,CN)
        if CN == "CC":
            current_size=len(cn_instances)
            if len(cn_instances) == 0:
                print("STDOUT: The resize script cannot work for a compute cluster if the size is there is no node in the cluster")
            else:
                for cn_instance in cn_instances:
                    max_index=-1
                    if int(cn_instance['display_name'].split('-')[-1]) > max_index:
                        max_index=int(cn_instance['display_name'].split('-')[-1])
                instance=computeClient.get_instance(cn_instances[0]['ocid']).data

                for i in range(args.number):
                    launch_instance_details=getLaunchInstanceDetails(instance,comp_ocid,cn_ocid,max_index,i)
                    ComputeClientCompositeOperations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
        else:
            size = current_size + args.number
            update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
            ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(ipa_ocid,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
        cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster_name)
        if CN == "CC":
            new_cn_instances = get_instances(comp_ocid,cn_ocid,CN)
            newsize=len(new_cn_instances)
        else:
            new_cn_instances = get_instances(comp_ocid,cn_ocid,CN)
            newsize=ip_summary.size
        updateTFState(inventory,cluster_name,newsize)
        if newsize == current_size:
            print("STDOUT: No node was added, please check the work requests of the Cluster Network and Instance Pool to see why")
            exit(1)