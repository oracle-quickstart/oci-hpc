import subprocess
import re
import requests
import oci
from datetime import datetime
import argparse
import os
import shlex



# change ownership of all files to opc so that the files can be copied
def changeOwner(path):
    cmd = f'sudo chown -R opc:opc {path}'
    run_cmd(cmd)


def getDateTime():
    # datetime object containing current date and time
    now = datetime.now()
    dt_string = now.strftime("%m%d%Y%H%M%S")
    return dt_string


# create directory to hold results
def createDir():
    # Parent Directory path
    parent_dir = "/tmp/"
    directory = getDateTime()
    # Path
    path = os.path.join(parent_dir, directory)
    try:
        os.mkdir(path)
    except OSError as error:
        print(error)
    return path


def run_cmd(cmd=None):
    """ Run command on shell"""
    cmd_split = shlex.split(cmd)
    try:
        results = subprocess.run(cmd_split, shell=False, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=True, encoding='utf8')
        output = results.stdout.splitlines()
    except subprocess.CalledProcessError as e_process_error:
        # print(f"!!! Error in running command [ {cmd}  ]. Fatal error exiting!!!")
        # print(f"Error code: {e_process_error.returncode} Output: {e_process_error.output}")
        return (9000, f"Error code: {e_process_error.returncode} Output: {e_process_error.output}")
    return output


def get_metadata():
    """ Make a request to metadata endpoint """
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()


def get_summary(comp_ocid,cluster_name):
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=signer)
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


def get_instances(comp_ocid,cn_ocid):
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=signer)
    instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_cluster_network_instances,comp_ocid,cn_ocid).data
    node_list = []
    for instance_summary in instance_summaries:
        node_list.append(instance_summary.display_name)
    return node_list


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


# this is the source of truth for cluster names and total number of nodes
def getResizeClusterNames(filepath):
    if filepath is None:
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
    else:
        out = subprocess.Popen(["cat "+filepath],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
        stdout,stderr = out.communicate()
        x = stdout.split("\n")
        del x[-1]
        cluster_name_set = set()
        for i in range(len(x)):
            cluster_name_set.add(x[i])
        return cluster_name_set


# this is the source of truth for total number of nodes in a cluster
def getResizeNodes(metadata, cluster_names, mode):
    if mode == 1 or mode == 2:
        resize_cluster_node_dict = {}
        str = "ocid1.instance."
        for cluster in cluster_names:
            out = subprocess.Popen(["/opt/oci-hpc/bin/resize.sh --cluster_name "+cluster],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
            stdout,stderr = out.communicate()
            x = stdout.split("\n")
            del x[-1]
            cluster_node_set = set()
            for i in range(len(x)):
                if str in x[i]:
                    split_str = x[i].split()
                    cluster_node_set.add(split_str[0].replace('"',''))
                if len(cluster_node_set) > 0:
                    resize_cluster_node_dict.update({cluster: cluster_node_set})
    if mode == 2:
        out = subprocess.Popen(["/opt/oci-hpc/bin/resize.sh list"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
        stdout,stderr = out.communicate()
        x = stdout.split("\n")
        del x[-1]
        permanent_cluster = ''
        cluster_node_set = set()
        for i in range(len(x)):
            if str in x[i]:
                permanent_cluster = metadata['displayName'].replace('-bastion','')
                if permanent_cluster in cluster_names:
                    return cluster_names, resize_cluster_node_dict
                else:
                    split_str = x[i].split()
                    cluster_node_set.add(split_str[0].replace('"',''))
        if len(cluster_node_set) > 0:
            resize_cluster_node_dict.update({permanent_cluster: cluster_node_set})
            cluster_names.add(permanent_cluster)
    return cluster_names, resize_cluster_node_dict


# given a cluster name, return all the nodes in that cluster
def getNodesInClusters(cluster_name):
    out = subprocess.Popen(["cat /etc/hosts | grep "+cluster_name+" | grep local.vcn | awk '{print $4}'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    nodes = set()
    x = stdout.split("\n")
    for i in range(0,len(x)-1):
        nodes.add(x[i])
    return nodes


def nodesFromEtcHosts(resize_cluster_names):
    etc_node_cluster_dict = {}
    etc_cluster_node_dict = {}
    for cluster in resize_cluster_names:
        etc_nodes = getNodesInClusters(cluster)
        for n in etc_nodes:
            etc_node_cluster_dict.update({n: cluster})
        etc_cluster_node_dict.update({cluster: etc_nodes})
    return etc_node_cluster_dict, etc_cluster_node_dict


def getConsoleNodeName(slurm_node_name):
    name = slurm_node_name + ".local.vcn"
    out = subprocess.Popen(["cat /etc/hosts | grep "+name+" | awk '{print $4}'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    node_name_output = stdout.split("\n")
    del node_name_output[-1]
    return node_name_output[0]


# get number of nodes and their state using slurm
def slurmGetNodes(resize_cluster_names, all_node_cluster_dict, path):
    out = subprocess.run(['sinfo','-hNr','-o','\"%T %D %N\"'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = out.stdout.decode("utf-8")
    x = lines.split("\n")
    del x[-1]
    good_node_states = set()
    good_node_states.add("allocated")
    good_node_states.add("idle")
    warning_node_dict = {}
    slurm_node_cluster_dict = {}
    for i in range(len(x)):
        split_str = x[i].split()
        node_state = split_str[0].replace('"','')
        node_name = split_str[2].replace('"','')
        proper_node_name = getConsoleNodeName(node_name)
        if proper_node_name is not None:
            if node_state not in good_node_states:
                warning_node_dict.update({proper_node_name: node_state})
            if proper_node_name in all_node_cluster_dict:
                slurm_node_cluster = all_node_cluster_dict[proper_node_name]
                if slurm_node_cluster in resize_cluster_names:
                    slurm_node_cluster_dict.update({proper_node_name: slurm_node_cluster})
            else:
                if path is None:
                    path = createDir()
                    changeOwner(path)
                f = open(path+"/slurmNumNodes.txt", "a")
                f.write(proper_node_name + " not found in resize" + "\n")
                f.close()
        else:
            if path is None:
                path = createDir()
                changeOwner(path)
            f = open(path+"/slurmNumNodes.txt", "a")
            f.write(node_name + " not found in /etc/hosts file for getting the oci console name" + "\n")
            f.close()
    return slurm_node_cluster_dict, warning_node_dict, path


def topologyGetNodes(resize_cluster_names, all_node_cluster_dict, path):
    str1 = "SwitchName=inactive"
    str2 = "Switches="
    out = subprocess.Popen(["cat /etc/slurm/topology.conf"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    x = stdout.split("\n")
    del x[-1]
    topo_node_cluster_dict = {}
    for i in range(len(x)):
        if str1 in x[i] or str2 in x[i] or x[i].startswith("#"):
            continue
        else:
            split_str = x[i].split()
            node_name_str = split_str[1].rsplit("=")
            node_name_1 = node_name_str[1].replace('"','')
            node_name = node_name_1.replace(' ','')
            res = re.findall(r'\[([^]]*)\]', node_name)
            if len(res) == 0:
                topo_node_name = getConsoleNodeName(node_name)
                if topo_node_name is not None:
                    if topo_node_name in all_node_cluster_dict:
                        topo_node_cluster = all_node_cluster_dict[topo_node_name]
                        if topo_node_cluster in resize_cluster_names:
                            topo_node_cluster_dict.update({topo_node_name: topo_node_cluster})
                    else:
                        if path is None:
                            path = createDir()
                            changeOwner(path)
                        f = open(path+"/topoNumNodes.txt", "a")
                        f.write(topo_node_name + " not found in resize" + "\n")
                        f.close()
                else:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/topoNumNodes.txt", "a")
                    f.write(node_name + " not found in /etc/hosts file for getting the oci console name" + "\n")
                    f.close()
            else:
                out = subprocess.Popen(["scontrol show hostnames "+node_name],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
                stdout,stderr = out.communicate()
                nodes = stdout.split("\n")
                del nodes[-1]
                for n in nodes:
                    oci_console_node_name = getConsoleNodeName(n)
                    if oci_console_node_name is not None:
                        if oci_console_node_name in all_node_cluster_dict:
                            topo_node_cluster = all_node_cluster_dict[oci_console_node_name]
                            if topo_node_cluster in resize_cluster_names:
                                topo_node_cluster_dict.update({oci_console_node_name: topo_node_cluster})
                        else:
                            if path is None:
                                path = createDir()
                                changeOwner(path)
                            f = open(path+"/topoNumNodes.txt", "a")
                            f.write(oci_console_node_name + " not found in resize" + "\n")
                            f.close()
                    else:
                        if path is None:
                            path = createDir()
                            changeOwner(path)
                        f = open(path+"/topoNumNodes.txt", "a")
                        f.write(node_name + " not found in /etc/hosts file for getting the oci console name" + "\n")
                        f.close()
    return topo_node_cluster_dict, path


def etcHostsSame(nodes, path):
    out = subprocess.Popen(["linecount=`cat /etc/hosts | wc -l ` ; lines=$((linecount-3)) ; tail -n $lines /etc/hosts | md5sum"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    x = stdout.split("\n")
    del x[-1]
    bastion_md5 = x[0].replace('"','')
    md5_set = set()
    md5_set.add(bastion_md5)
    out = subprocess.Popen(["pdsh -w "+nodes+" 'linecount=`cat /etc/hosts | wc -l ` ; lines=$((linecount-3)) ; tail -n $lines /etc/hosts | md5sum'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    x = stdout.split("\n")
    del x[-1]
    str = "exit"
    for i in range(len(x)):
        split_str = x[i].split(':')
        if str in x[i]:
            if path is None:
                path = createDir()
                changeOwner(path)
            f = open(path+"/etcHostsMD5Sum.txt", "a")
            f.write(split_str[1] + " not ssh-able at the moment" + "\n")
            f.close()
            continue
        else:
            md5 = split_str[1].lstrip()
            if md5 != bastion_md5:
                if path is None:
                    path = createDir()
                    changeOwner(path)
                f = open(path+"/etcHostsMD5Sum.txt", "a")
                f.write("/etc/hosts file does not match on " + split_str[0] + "\n")
                f.close()
                md5_set.add(md5)
    if len(md5_set) > 1:
        print("/etc/hosts on bastion and nodes is different")
    else:
        print("/etc/hosts is same on bastion and all nodes that are ssh-able")
    return path


def ociCommand(metadata, cluster_names):
    comp_ocid=metadata['compartmentId']
    oci_node_cluster_dict = {}
    node_list = []
    for cluster in cluster_names:
        cn_summary,ip_summary,CN = get_summary(comp_ocid,cluster)
        if cn_summary is not None:
            cn_ocid = cn_summary.id
            node_list = get_instances(comp_ocid, cn_ocid)
            for node in node_list:
                oci_node_cluster_dict.update({node: cluster})
        elif ip_summary is not None:
            cn_ocid = ip_summary.id
            node_list = get_instances(comp_ocid, cn_ocid)
            for node in node_list:
                oci_node_cluster_dict.update({node: cluster})
    return oci_node_cluster_dict


def inventoryNodes(metadata, cluster_names):
    inventory_node_cluster_dict = {}
    permanent_cluster = metadata['displayName'].replace('-bastion','')
    for cluster in cluster_names:
        if cluster == permanent_cluster:
            inventory = "/etc/ansible/hosts"
            inventory_dict = parse_inventory(inventory)
            inv_list = inventory_dict["compute_configured"]
            for i in inv_list:
                split_str = i.split()
                node_name = split_str[0]
                inventory_node_cluster_dict.update({node_name: cluster})
        else:
            inventory = "/opt/oci-hpc/autoscaling/clusters/"+cluster+"/inventory"
            inventory_dict = parse_inventory(inventory)
            inv_list = inventory_dict["compute_configured"]
            for i in inv_list:
                split_str = i.split()
                node_name = split_str[0]
                inventory_node_cluster_dict.update({node_name: cluster})
    return inventory_node_cluster_dict


def pcie_check(hostfile, path):
    out = subprocess.Popen(["sudo cp /opt/oci-hpc/bin/pcie.sh ~/."],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    out = subprocess.Popen(["for h in `less "+hostfile+"` ; do echo $h ; ssh $h \"~/pcie.sh\" ; done > "+path+"/pcie-output"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()

def gpu_throttle(hostfile, path):
    out = subprocess.Popen(["sudo cp /opt/oci-hpc/bin/gpu_throttle.sh ~/."],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    out = subprocess.Popen(["for h in `less "+hostfile+"` ; do echo $h ; ssh $h \"~/gpu_throttle.sh\" ; done > "+path+"/gpu-throttle-output"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()

def getResizeCluster(args, metadata):
    resize_cluster_names = []
    resize_cluster_node_dict = {}
    resize_node_cluster_dict = {}
    resize_cluster_names = getResizeClusterNames(args.cluster_names)
    resize_cluster_names, resize_cluster_node_dict = getResizeNodes(metadata, resize_cluster_names, 1)

    if len(resize_cluster_names) == 0 or len(resize_cluster_node_dict) == 0:
        print("There are no clusters available")
    else:
        for k, v in resize_cluster_node_dict.items():
            for v1 in v:
                resize_node_cluster_dict[v1] = k

    return resize_cluster_names, resize_cluster_node_dict, resize_node_cluster_dict

###############

parser = argparse.ArgumentParser(description = 'Perform these checks. \
    1. Check the number of nodes is consistent across resize, /etc/hosts, slurm, topology.conf, OCI console, inventory files. \
    2. PCIe bandwidth check. \
    3. GPU Throttle check \
    4. Standalone /etc/hosts md5 sum validation \
    Options: \
    --cluster_names <path to file> : Give a file that contains all the cluster names for option 1 and this will be considered as source of truth. \
        If not given, then the cluster names in the directory /opt/oci-hpc/autoscaling/clusters/ along with any permanent cluster associated \
        with the bastion will be considered as source of truth. ')
parser.add_argument('-n', '--num_nodes', help = "Check the number of nodes is consistent across resize.sh, /etc/hosts, slurm, topology.conf, OCI console, inventory files. \
    Also check /etc/hosts is same as bastion across all hosts. If -cn option is provided along with this, then that file will be considered. If not, nodes \
        resize will be considered. ")
parser.add_argument('-cn', '--cluster_names', help = "Provide a file that contains list of all cluster names for the above validation")
parser.add_argument('-p', '--pcie_file', help = "Provide a file that contains list of hosts on which to perform pcie check")
parser.add_argument('-g', '--gpu_throttle', help = "Provide a file that contains list of hosts on which to perform gpu throttle check")
parser.add_argument('-e', '--etc_hosts', help = "Provide a file that contains list of hosts on which to perform md5 sum check to match with bastion")

args = parser.parse_args()

metadata=get_metadata()

path = None

resize_cluster_names = []
resize_cluster_node_dict = {}
resize_node_cluster_dict = {}

if args.num_nodes is not None:
    resize_cluster_names, resize_cluster_node_dict, resize_node_cluster_dict = getResizeCluster(args, metadata)

    if len(resize_cluster_names) > 0:

        # get all clusters and its corresponding nodes --> this is required to get the cluster name of the nodes from slurm and topology.conf \
        # so as to filter out clusters if -cn option is given
        all_cluster_names = []
        all_cluster_node_dict = {}
        all_node_cluster_dict = {}
        all_cluster_names = getResizeClusterNames(None)
        all_cluster_names, all_cluster_node_dict = getResizeNodes(metadata, all_cluster_names, 2)
        if len(all_cluster_names) == 0 or len(all_cluster_node_dict) == 0:
            print("There are no clusters available")
        else:
            for k, v in all_cluster_node_dict.items():
                for v1 in v:
                    all_node_cluster_dict[v1] = k

        etc_node_cluster_dict, etc_cluster_node_dict = nodesFromEtcHosts(resize_cluster_names)

        slurm_node_cluster_dict, warning_node_dict, path = slurmGetNodes(resize_cluster_names, all_node_cluster_dict, path)

        topo_node_cluster_dict, path = topologyGetNodes(resize_cluster_names, all_node_cluster_dict, path)

        inventory_node_cluster_dict = inventoryNodes(metadata, resize_cluster_names)

        oci_node_cluster_dict = ociCommand(metadata, resize_cluster_names)

        if resize_node_cluster_dict == etc_node_cluster_dict:
            print("Number of nodes in /etc/hosts on bastion is same as resize")
        else:
            for key in resize_node_cluster_dict.keys():
                if not key in etc_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/etcHostsNumNodes.txt", "a")
                    f.write(key + " is not in etc hosts" + "\n")
                    f.close()
            for key in etc_node_cluster_dict.keys():
                if not key in resize_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/etcHostsNumNodes.txt", "a")
                    f.write(key + " is not in resize list" + "\n")
                    f.close()

        if resize_node_cluster_dict == slurm_node_cluster_dict:
            print("Number of nodes from slurm is same as resize")
        else:  
            for key in resize_node_cluster_dict.keys():
                if not key in slurm_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/slurmNumNodes.txt", "a")
                    f.write(key + " is not in slurm" + "\n")
                    f.close()
            for key in slurm_node_cluster_dict.keys():
                if not key in resize_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/slurmNumNodes.txt", "a")
                    f.write(key + " is not in resize list" + "\n")
                    f.close()

        if len(warning_node_dict) > 0:
            for key in warning_node_dict.keys():
                if path is None:
                    path = createDir()
                    changeOwner(path)
                f = open(path+"/slurmWarnNodes.txt", "a")
                f.write(key + " is in slurm state " + warning_node_dict[key] + "\n")
                f.close()

        if resize_node_cluster_dict == topo_node_cluster_dict:
            print("Number of nodes from topology is same as resize")
        else:
            for key in resize_node_cluster_dict.keys():
                if not key in topo_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/topoNumNodes.txt", "a")
                    f.write(key + " is not in topology.conf file" + "\n")
                    f.close()
            for key in topo_node_cluster_dict.keys():
                if not key in resize_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/topoNumNodes.txt", "a")
                    f.write(key + " is not in resize list" + "\n")
                    f.close()

        if resize_node_cluster_dict == inventory_node_cluster_dict:
            print("Number of nodes from inventory is same as resize")
        else:
            for key in resize_node_cluster_dict.keys():
                if not key in inventory_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/inventoryNumNodes.txt", "a")
                    f.write(key + " is not in inventory file" + "\n")
                    f.close()
            for key in inventory_node_cluster_dict.keys():
                if not key in resize_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/inventoryNumNodes.txt", "a")
                    f.write(key + " is not in resize list" + "\n")
                    f.close()

        if resize_node_cluster_dict == oci_node_cluster_dict:
            print("Number of nodes from oci cli is same as resize")
        else:
            for key in resize_node_cluster_dict.keys():
                if not key in oci_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/ociCliNumNodes.txt", "a")
                    f.write(key + " not found using oci cli" + "\n")
                    f.close()
            for key in oci_node_cluster_dict.keys():
                if not key in resize_node_cluster_dict:
                    if path is None:
                        path = createDir()
                        changeOwner(path)
                    f = open(path+"/ociCliNumNodes.txt", "a")
                    f.write(key + " is not in resize list" + "\n")
                    f.close()

        node_list = list(map(' '.join, resize_cluster_node_dict.values()))
        nodes_space = ' '.join(str(s) for s in node_list)
        split_str = nodes_space.split()
        nodes_comma = ','.join(str(s) for s in split_str)
        path = etcHostsSame(nodes_comma, path)

if args.num_nodes is None and args.etc_hosts is not None:
    hostfile = args.etc_hosts
    out = subprocess.Popen(["cat "+hostfile],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    x = stdout.split("\n")
    del x[-1]
    nodes_comma = ','.join(str(s) for s in x)
    etcHostsSame(nodes_comma, path)

hostFileWritten = False
if args.pcie_file is not None:
    if args.pcie_file == 'y' or args.pcie_file == 'Y':
        if args.cluster_names is not None:
            if len(resize_node_cluster_dict) == 0:
                resize_cluster_names, resize_cluster_node_dict, resize_node_cluster_dict = getResizeCluster(args, metadata)
                if len(resize_cluster_names) == 0:
                    exit()
            if path is None:
                path = createDir()
                changeOwner(path)
            f = open(path+"/host.txt", "a")
            for v in resize_node_cluster_dict.keys():
                hostFileWritten = True
                f.write(str(v) + "\n")
            f.close()
            pcie_hostfile = path+"/host.txt"
            pcie_check(pcie_hostfile, path)
        else:
            print("Provide cluster_names file or hosts file to run pcie check")
    else:
        pcie_hostfile = args.pcie_file
        if path is None:
            path = createDir()
            changeOwner(path)
        pcie_check(pcie_hostfile, path)

if args.gpu_throttle is not None:
    if args.gpu_throttle == 'y' or args.gpu_throttle == 'Y':
        if args.cluster_names is not None:
            if hostFileWritten is False:
                if len(resize_node_cluster_dict) == 0:
                    resize_cluster_names, resize_cluster_node_dict, resize_node_cluster_dict = getResizeCluster(args, metadata)
                    if len(resize_cluster_names) == 0:
                        exit()
                if path is None:
                    path = createDir()
                    changeOwner(path)
                f = open(path+"/host.txt", "a")
                for v in resize_node_cluster_dict.keys():
                    f.write(str(v) + "\n")
                f.close()
            gpu_hostfile = path+"/host.txt"
            gpu_throttle(gpu_hostfile, path)
        else:
            print("Provide cluster_names file or hosts file to run gpu throttle check")
    else:
        gpu_hostfile = args.gpu_throttle
        if path is None:
            path = createDir()
            changeOwner(path)
        gpu_throttle(gpu_hostfile, path)

if path is not None:
    print(f"Output is in folder: {path}")

