import subprocess
import time
import shutil
import os
from utils import backup_inventory, parse_inventory, write_inventory, get_instances, getreachable
from ociobj import ocicore, ocicluster

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

def destroy_unreachable_reconfigure(ocicluster,ocicore,nodes_to_remove,playbook):
    if not os.path.isfile("/etc/ansible/hosts"):
        print("STDOUT: There is no inventory file, are you on the controller? The cluster has not been resized")
        exit(1)
    backup_inventory(ocicluster.inventory)
    inventory_dict = parse_inventory(ocicluster.inventory)
    tmp_inventory_destroy="/tmp/"+ocicluster.inventory.replace('/','_')+"_destroy"
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
        instances = get_instances(ocicluster, ocicore)
        for instance in instances:
            if instance['display_name'] in nodes_to_remove and not instance['ip'] in ips_to_remove:
                ips_to_remove.append(instance['ip'])
        if len(ips_to_remove) != len(nodes_to_remove):
            print("STDOUT: Some nodes are removed in OCI and removed from the inventory")
            print("STDOUT: Try rerunning with the --nodes option and a list of IPs or Slurm Hostnames to cleanup the controller")
    write_inventory(inventory_dict,tmp_inventory_destroy)
    if not len(ips_to_remove) or not ocicluster.slurm_name_change:
        if not len(ips_to_remove):
            print("STDOUT: No hostname found, trying anyway with "+" ".join(nodes_to_remove))
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
        tmp_inventory="/tmp/"+ocicluster.inventory.replace('/','_')
        write_inventory(inventory_dict,tmp_inventory)
        os.system('sudo mv '+tmp_inventory+' '+ocicluster.inventory)
        os.system('')
    return update_flag

def destroy_reconfigure(ocicluster,ocicore,nodes_to_remove,playbook,remove_unreachable):
    if not os.path.isfile("/etc/ansible/hosts"):
        print("STDOUT: There is no inventory file, are you on the controller? The cluster has not been resized")
        exit(1)
    backup_inventory(ocicluster.inventory)
    inventory_dict = parse_inventory(ocicluster.inventory)
    inventory_dict['compute_to_destroy']=[]
    instances = get_instances(ocicluster, ocicore)
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
    tmp_inventory_destroy="/tmp/"+ocicluster.inventory.replace('/','_')+"_destroy"
    write_inventory(inventory_dict,tmp_inventory_destroy)
    update_flag = update_cluster(tmp_inventory_destroy,playbook)
    if update_flag == 0:
        os.remove(tmp_inventory_destroy)
        inventory_dict['compute_to_destroy']=[]
        tmp_inventory="/tmp/"+ocicluster.inventory.replace('/','_')
        write_inventory(inventory_dict,tmp_inventory)
        os.system('sudo mv '+tmp_inventory+' '+ocicluster.inventory)
        os.system('')
    return update_flag

def add_reconfigure(ocicluster,ocicore,specific_hosts=None):
    instances = get_instances(ocicluster, ocicore)
    backup_inventory(ocicluster.inventory)
    inventory_dict = parse_inventory(ocicluster.inventory)
    username="opc"
    for inv_vars in inventory_dict["all:vars"]:
        if inv_vars.startswith("compute_username"):
            username=inv_vars.split("compute_username=")[1].strip()
            break
    reachable_instances=instances
    unreachable_instances=[]
    if not os.path.isfile(ocicluster.inventory):
        print("STDOUT: There is no inventory file, are you on the controller? The cluster has been resized but not reconfigured")
        exit(1)
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
    hostfile=open("/tmp/hosts_"+ocicluster.cluster_name,'w')
    hostfile.write("\n".join(host_to_wait_for))
    hostfile.close()
    tmp_inventory_add="/tmp/"+ocicluster.inventory.replace('/','_')+"_add"
    write_inventory(inventory_dict,tmp_inventory_add)
    update_flag = update_cluster(tmp_inventory_add,ocicluster.playbooks_dir+"resize_add.yml",hostfile="/tmp/hosts_"+ocicluster.cluster_name)
    if update_flag == 0:
        os.remove(tmp_inventory_add)
        for line in inventory_dict['compute_to_add']:
            inventory_dict['compute_configured'].append(line)
        inventory_dict['compute_to_add']=[]
        tmp_inventory="/tmp/"+ocicluster.inventory.replace('/','_')
        write_inventory(inventory_dict,tmp_inventory)
        os.system('sudo mv '+tmp_inventory+' '+ocicluster.inventory)
    else:
        print("STDOUT: The reconfiguration to add the node(s) had an error")
        print("STDOUT: Try rerunning this command: ansible-playbook -i "+tmp_inventory_add+' '+ocicluster.playbooks_dir+"resize_add.yml" )
        exit(1)

def reconfigure(ocicluster,ocicore,crucial=False):
    instances = get_instances(ocicluster, ocicore)
    if not os.path.isfile(ocicluster.inventory):
        print("STDOUT: There is no inventory file, are you on the controller? Reconfigure did not happen")
        exit(1)
    backup_inventory(ocicluster.inventory)
    inventory_dict = parse_inventory(ocicluster.inventory)
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
    hostfile=open("/tmp/hosts_"+ocicluster.cluster_name,'w')
    hostfile.write("\n".join(host_to_wait_for))
    hostfile.close()
    tmp_inventory_reconfig="/tmp/"+ocicluster.inventory.replace('/','_')+"_reconfig"
    write_inventory(inventory_dict,tmp_inventory_reconfig)
    if ocicluster.autoscaling:
        playbook=ocicluster.playbooks_dir+"new_nodes.yml"
    else:
        playbook=ocicluster.playbooks_dir+"site.yml"
    if crucial:
        playbook=ocicluster.playbooks_dir+"resize_remove.yml"
    update_flag = update_cluster(tmp_inventory_reconfig,playbook,hostfile="/tmp/hosts_"+ocicluster.cluster_name)
    if update_flag == 0:
        os.system('sudo mv '+tmp_inventory_reconfig+' '+ocicluster.inventory)
    else:
        print("The reconfiguration had an error")
        print("Try rerunning this command: ansible-playbook -i "+tmp_inventory_reconfig+' '+playbook )