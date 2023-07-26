from audioop import reverse
import collections
import subprocess
import argparse

# get idle, allocated, and all other nodes
def getAllNodes():
    out = subprocess.run(['sinfo','-hNr','-o','\"%T %N %R\"'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    lines = out.stdout.decode("utf-8")
    x = lines.split("\n")
    del x[-1]
    partition_dict = {}
    for i in range(len(x)):
        split_str = x[i].split()
        partition_name = split_str[2].replace('"','')
        idle_nodes = set()
        allocated_nodes = set()
        down_nodes = set()
        drained_nodes = set()
        all_other_nodes = set()
        info_dict = {}
        if len(partition_dict) != 0:
            if partition_name in partition_dict:
                retrieved_dict = partition_dict[partition_name]
                if "idle" in retrieved_dict:
                    idle_nodes = retrieved_dict["idle"]
                if "allocated" in retrieved_dict:
                    allocated_nodes = retrieved_dict["allocated"]
                if "down" in retrieved_dict:
                    down_nodes = retrieved_dict["down"]
                if "drained" in retrieved_dict:
                    drained_nodes = retrieved_dict["drained"]
                if "others" in retrieved_dict:
                    all_other_nodes = retrieved_dict["others"]
                info_dict.update({"idle": idle_nodes})
                info_dict.update({"allocated": allocated_nodes})
                info_dict.update({"down": down_nodes})
                info_dict.update({"drained": drained_nodes})
                info_dict.update({"others": all_other_nodes})
        if (split_str[0].replace('"','') == "idle"):
            idle_nodes.add(split_str[1].replace('"',''))
            info_dict.update({"idle": idle_nodes})
        elif (split_str[0].replace('"','') == "allocated"):
            allocated_nodes.add(split_str[1].replace('"',''))
            info_dict.update({"allocated": allocated_nodes})
        elif (split_str[0].replace('"','') == "down"):
            down_nodes.add(split_str[1].replace('"',''))
            info_dict.update({"down": down_nodes})
        elif (split_str[0].replace('"','') == "drained"):
            drained_nodes.add(split_str[1].replace('"',''))
            info_dict.update({"drained": drained_nodes})
        else:
            all_other_nodes.add(split_str[1].replace('"',''))
            info_dict.update({"others": all_other_nodes})
        partition_dict.update({partition_name: info_dict})
    return partition_dict


# given a cluster name, return all the nodes in that cluster
def getNodesInClusters(cluster_name):
    out = subprocess.Popen(["cat /etc/hosts | grep "+cluster_name+" | grep local.vcn | awk '{print $2}'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    nodes = set()
    x = stdout.split("\n")
    for i in range(0,len(x)-1):
        nodes.add(x[i])
    return nodes


# find out all available clusters
def getClusterNames():
    out = subprocess.Popen(["cat /etc/hosts | grep \"END ANSIBLE MANAGED BLOCK\" | awk '{print $6}'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    x = stdout.split("\n")
    del x[-1]
    cluster_list = []
    for cluster in x:
        if (cluster == "BASTION"):
            continue
        else:
            cluster_list.append(cluster)
    return cluster_list


def printClusterAndNodes(nodes_dict):
    if len(nodes_dict) == 0:
        exit()
    print ("{:<20} {:<20} {:<15} {:<15} {:<15} {:<15} {:<15} {:<15}".format('Partition Name','Cluster Name','Available','Busy','Down','Drained','Others','Total'))
    nodes_dict = collections.OrderedDict(sorted(nodes_dict.items()))
    for k, v in nodes_dict.items():
        clusters_in_partition = collections.OrderedDict(sorted(v.items()))
        for cluster, nodes in clusters_in_partition.items():
            idle_total = 0
            allocated_total = 0
            down_total = 0
            drained_total = 0
            others_total = 0
            total = 0
            for key in nodes:
                if (key == "idle"):
                    idle_total = len(clusters_in_partition[cluster][key])
                elif (key == "allocated"):
                    allocated_total = len(clusters_in_partition[cluster][key])
                elif (key == "down"):
                    down_total = len(clusters_in_partition[cluster][key])
                elif (key == "drained"):
                    drained_total = len(clusters_in_partition[cluster][key])
                elif (key == "others"):
                    others_total = len(clusters_in_partition[cluster][key])
                total = idle_total + allocated_total + down_total + drained_total + others_total
            print ("{:<20} {:<20} {:<15} {:<15} {:<15} {:<15} {:<15} {:<15}".format(k, cluster, idle_total, allocated_total, down_total, drained_total, others_total, total))


def getClusterAndNodes(cluster_list, include_cluster_list, partition_dict):
    partition_nodes_dict = {}
    iterate_cluster_list = []
    if len(include_cluster_list):
        iterate_cluster_list = include_cluster_list
    else:
        iterate_cluster_list = cluster_list
    for cluster in iterate_cluster_list:
        if cluster in cluster_list:
            nodes_dict = {}
            nodes_in_cluster = set()
            cluster_idle_nodes = set()
            cluster_allocated_nodes = set()
            cluster_down_nodes = set()
            cluster_drained_nodes = set()
            cluster_all_other_nodes = set()
            cluster_dict = {}
            nodes_in_cluster = getNodesInClusters(cluster)
            one_node = "test"
            for node in nodes_in_cluster:
                one_node = node.split('-')
                break
            partition_name = one_node[0]
            cluster_idle_nodes = nodes_in_cluster.intersection(partition_dict[partition_name]["idle"])
            cluster_allocated_nodes = nodes_in_cluster.intersection(partition_dict[partition_name]["allocated"])
            cluster_down_nodes = nodes_in_cluster.intersection(partition_dict[partition_name]["down"])
            cluster_drained_nodes = nodes_in_cluster.intersection(partition_dict[partition_name]["drained"])
            cluster_all_other_nodes = nodes_in_cluster.intersection(partition_dict[partition_name]["others"])
            cluster_dict.update({"idle": cluster_idle_nodes})
            cluster_dict.update({"allocated": cluster_allocated_nodes})
            cluster_dict.update({"down": cluster_down_nodes})
            cluster_dict.update({"drained": cluster_drained_nodes})
            cluster_dict.update({"others": cluster_all_other_nodes})
            if len(partition_nodes_dict) != 0:
                if partition_name in partition_nodes_dict:
                    nodes_dict = partition_nodes_dict[partition_name]
                    nodes_dict[cluster] = cluster_dict
            nodes_dict[cluster] = cluster_dict
            partition_nodes_dict.update({partition_name: nodes_dict})
        else:
            print("Not a valid cluster name: " + cluster)
    return partition_nodes_dict


def printGetClusterAndIdleNodes(nodes_dict):
    partition_idle_nodes = {}
    print("\n-------Partitions with respective clusters and available nodes-------")
    nodes_dict = collections.OrderedDict(sorted(nodes_dict.items()))
    for key, value in nodes_dict.items():
        node_list = []
        clusters_in_partition = collections.OrderedDict(sorted(value.items()))
        print("\n--", key, "--")
        for cluster in clusters_in_partition:
            idle_list = list(clusters_in_partition[cluster]["idle"])
            if not idle_list:
                continue
            nodelist_prefix = []
            numbers_int = []
            for i in idle_list:
                x = i.split("-")
                if not nodelist_prefix:
                    nodelist_prefix = x[:3]
                numbers_int.append(int(x[-1]))
            numbers_int.sort()
            numbers_str = [str(n) for n in numbers_int]
            compute_list = [nodelist_prefix[0] + "-" + nodelist_prefix[1] + "-" + nodelist_prefix[2] + "-" + s for s in numbers_str]
            print(cluster, '->', compute_list)
            node_list.append(len(compute_list))
        partition_idle_nodes.update({key: node_list})
    return partition_idle_nodes


def maxNodesEvenDistributed(partition_idle_nodes_dict):
    print("\n-------Maximum number of nodes distributed evenly per partition-------")
    partition_idle_nodes_dict = collections.OrderedDict(sorted(partition_idle_nodes_dict.items()))
    for key, node_list in partition_idle_nodes_dict.items():
        if len(node_list):
            node_list.sort(reverse=True)
            max_node_list = []
            for i in range(len(node_list)):
                max_node_list.append(node_list[i]*(i+1))
            max_nodes = max(max_node_list)
            print(key, "->", max_nodes)
        else:
            print(key, "->", 0)


parser = argparse.ArgumentParser(description='Information about all the partitions and their respective clusters, and maximum number of nodes distributed evenly per partition')
parser.add_argument('--include_cluster_names', help="Provide a space separated list of cluster names to be considered for displaying the \
    information about clusters and maximum number of nodes distributed evenly per partition",nargs='+')
args = parser.parse_args()
input_cluster_names = args.include_cluster_names
if input_cluster_names is None:
    include_cluster_list = []
else:
    input_cluster_set = set(input_cluster_names)
    include_cluster_list = list(input_cluster_set)


partition_dict = getAllNodes()
all_cluster_list = getClusterNames()
nodes_dict = getClusterAndNodes(all_cluster_list, include_cluster_list, partition_dict)
printClusterAndNodes(nodes_dict)
partition_idle_nodes = printGetClusterAndIdleNodes(nodes_dict)
maxNodesEvenDistributed(partition_idle_nodes)
