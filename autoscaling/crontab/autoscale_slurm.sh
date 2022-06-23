#!/bin/python
import subprocess
import datetime
import time
import sys, os
import traceback
import json
import copy
import yaml

lockfile = "/tmp/autoscaling_lock"
queues_conf_file = "/opt/oci-hpc/conf/queues.conf"

# seconds for a cluster to stay alive
idle_time=600 #seconds

script_path='/opt/oci-hpc/bin'

def israckaware():
    rackware=False
    if os.path.isfile("/opt/oci-hpc/conf/variables.tf"):
        variablefile=open("/opt/oci-hpc/conf/variables.tf",'r')
        for line in variablefile:
            if "\"rack_aware\"" in line and ("true" in line or "True" in line or "yes" in line or "Yes" in line) :
                rackware=True
                break
    return rackware

def getTopology():
    topology={}
    if os.path.isfile("/etc/slurm/topology.conf"):
        topologyfile=open("/etc/slurm/topology.conf",'r')
        for line in topologyfile:
            if israckaware:
                splittedline=line.strip().split(" Nodes=")
                if len(splittedline)==1:
                    continue
                switchName=splittedline[0].split('SwitchName=')[1]
                if len(switchName.split(':')) == 1:
                    clusterName=switchName
                else :
                    clusterName=':'.join(splittedline[0].split('SwitchName=')[1].split(':')[:-1])
                if clusterName in topology.keys():
                    topology[clusterName]=topology[clusterName]+splittedline[1].split(',')
                else:
                    topology[clusterName]=splittedline[1].split(',')
            else:
                splittedline=line.strip().split(" Nodes=")
                try:
                    clusterName=splittedline[0].split('SwitchName=')[1]
                except:
                    continue
                topology[clusterName]=splittedline[1].split(',')
    return topology
# Get the list of Jobs in all states
def getJobs():
    out = subprocess.Popen(['squeue','-O','STATE,JOBID,FEATURE:100,NUMNODES,Dependency,Partition,UserName'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()
    return stdout.split("\n")[1:]

def getClusters():
    out = subprocess.Popen(['sinfo','-hNr','-o','\"%T %E %D %N\"'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()
    return stdout.split("\n")

def getNodeDetails(node):
    out = subprocess.Popen(['sinfo','-h','-n',node,'-o','"%f %R"'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()
    for pot_output in stdout.split("\n"):
        if not "(null)" in pot_output and pot_output.strip() != '':
            output=pot_output
            if output[0] == '"':
                output=output[1:]
            if output[-1] == '"':
                output=output[:-1]
        else:
            continue
    return output

def getIdleTime(node):
    out = subprocess.Popen(["sacct -X -n -S 01/01/01 -N "+node+" -o End | tail -n 1"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True)
    stdout,stderr = out.communicate()
    last_end_time = None
    try:
        last_end_time = datetime.datetime.strptime(stdout.strip(),"%Y-%m-%dT%H:%M:%S")
    except:
        pass
    out = subprocess.Popen(["scontrol show node "+node+" | grep SlurmdStartTime | awk '{print $2}'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True)
    stdout,stderr = out.communicate()
    try: 
        cluster_start_time=datetime.datetime.strptime(stdout.split("\n")[0].split("=")[1],"%Y-%m-%dT%H:%M:%S")
    except:
        print "The cluster start time of node "+node+" could not be found"
        print "There seems to be an issue with the command"
        print "scontrol show node "+node+" | grep SlurmdStartTime | awk '{print $2}'"
        print "Here is the output it generated"
        print stdout
        print "The cluster will be deleted"
        cluster_start_time=datetime.datetime.now()-datetime.timedelta(hours=24)
    if last_end_time is None:
        right_time=cluster_start_time
    else:
        right_time=max([cluster_start_time,last_end_time])
    return ( datetime.datetime.now() - right_time ).total_seconds()

# Get the last time a node state was changed. This is used to get how long a cluster has been idle for
def getQueueConf(file):
    with open(queues_conf_file) as file:
        try:
            data = yaml.load(file,Loader=yaml.FullLoader)
        except:
            data = yaml.load(file)
        return data["queues"]

def getQueue(config,queue_name):
    for queue in config:
        if queue["name"]==queue_name:
            return queue
    return None

def getDefaultsConfig(config,queue_name):
    for partition in config:
        if queue_name == partition["name"]:
            for instance_type in partition["instance_types"]:
                if "default" in instance_type.keys():
                    if instance_type["default"]:
                        return {"queue":partition["name"], "instance_type":instance_type["name"], "shape":instance_type["shape"], "cluster_network":instance_type["cluster_network"], "instance_keyword":instance_type["instance_keyword"]}
            if len(partition["instance_types"])>0:
                instance_type=partition["instance_types"][0]
                print "No default configuration was found, there may be a problem in your queues.conf file"
                print "Selecting "+instance_type["name"]+" as default"
                return {"queue":partition["name"], "instance_type":instance_type["name"], "shape":instance_type["shape"], "cluster_network":instance_type["cluster_network"], "instance_keyword":instance_type["instance_keyword"]}
    print "The queue "+queue_name+" was not found in the queues.conf file"
    return None

def getJobConfig(config,queue_name,instance_type_name):
    for partition in config:
        if queue_name == partition["name"]:
            for instance_type in partition["instance_types"]:
                if instance_type_name == instance_type["name"]:
                    return {"queue":partition["name"], "instance_type":instance_type["name"], "shape":instance_type["shape"], "cluster_network":instance_type["cluster_network"], "instance_keyword":instance_type["instance_keyword"]}
    return None

def getQueueLimits(config,queue_name,instance_type_name):
    for partition in config:
        if queue_name == partition["name"]:
            for instance_type in partition["instance_types"]:
                if instance_type_name == instance_type["name"]:
                    return {"max_number_nodes": int(instance_type["max_number_nodes"]), "max_cluster_size": int(instance_type["max_cluster_size"]),"max_cluster_count": int(instance_type["max_cluster_count"])}
    return {"max_number_nodes": 0, "max_cluster_size": 0,"max_cluster_count": 0}

def getInstanceType(config,queue_name,instance_keyword):
    for partition in config:
        if queue_name == partition["name"]:
            for instance_type in partition["instance_types"]:
                if instance_keyword == instance_type["instance_keyword"]:
                    return instance_type["name"]
    return None

def isPermanent(config,queue_name,instance_type_name):
    for partition in config:
        if queue_name == partition["name"]:
            for instance_type in partition["instance_types"]:
                if instance_type_name == instance_type["name"]:
                    return instance_type["permanent"]
    return None

def getAllClusterNames(config):
    availableNames={}
    for partition in config:
        availableNames[partition["name"]]={}
        for instance_type in partition["instance_types"]:
            availableNames[partition["name"]][instance_type["name"]]=range(1,int(instance_type["max_cluster_count"])+1)
    return availableNames

def getClusterName(topology,node):
    for key in topology.keys():
        if node in topology[key]:
            return key
    return None

def getstatus_slurm():
    cluster_to_build=[]
    topology=getTopology()

    # Get cluster to build
    for line in getJobs():
        if len(line.split())>3:
            if line.split()[0].strip() == 'PENDING' and 'null' in line.split()[4].strip():
                queue = line.split()[5].strip()
                user = line.split()[6].strip()
                features=line.split()[2].split('&')
                instanceType= None
                possible_types=[inst_type["name"] for inst_type in getQueue(config,queue)["instance_types"]]
                default_config=getDefaultsConfig(config,queue)
                if instanceType is None:
                    instanceType = default_config["instance_type"]
                    for feature in features:
                        if feature in possible_types:
                            instanceType=feature
                            break

                nodes=int(line.split()[3])
                jobID=int(line.split()[1])
                cluster_to_build.append([nodes,instanceType,queue,jobID,user])

    cluster_to_destroy=[]
    current_nodes={}
    building_nodes={}
    running_cluster=[]
    nodes_to_destroy_temp={}
    nodes_to_destroy={}
    # Get Cluster to destroy, or nodes to destroy
    for line in getClusters():
        if len(line.split()) == 0:
            break
        old_nodes=line.split()[-1].split(',')
        brokenListOfNodes=False
        nodes=[]
        for node in old_nodes:
            if brokenListOfNodes:
                if ']' in node:
                    brokenListOfNodes=False
                    nodes.append(currentNode+','+node)
                else:
                    currentNode=currentNode+','+node
            elif '[' in node and not ']' in node:
                brokenListOfNodes=True
                currentNode=node
            else:
                nodes.append(node)
        clusters = []
        for node in nodes:
            if node[-1]=="\"":
                node=node[:-1]
            if node[0]=="\"":
                node=node[1:]
            details=getNodeDetails(node).split(' ')
            features=details[0].split(',')
            queue=details[-1]
            clustername=getClusterName(topology,node)
            if clustername is None:
                continue
            instanceType=features[-1]
            if queue in current_nodes.keys():
                if instanceType in current_nodes[queue].keys():
                    current_nodes[queue][instanceType]+=1
                else:
                    current_nodes[queue][instanceType]=1
            else:
                current_nodes[queue]={instanceType:1}
            if line.split()[0] == '\"idle':
                if not os.path.isdir(os.path.join(clusters_path,clustername)):
                    continue
                node_idle_time=getIdleTime(node)
                if node_idle_time<idle_time:
                    print clustername + " is too young to die : "+str(node_idle_time) + " : "+node
                    continue
                if isPermanent(config,queue,instanceType) is None :
                    continue
                elif isPermanent(config,queue,instanceType):
                    continue
                if not clustername in nodes_to_destroy_temp.keys():
                    nodes_to_destroy_temp[clustername]=[]
                nodes_to_destroy_temp[clustername].append(node)
            elif line.split()[0] == '\"allocated' or line.split()[0] == '\"mixed':
                if not clustername in running_cluster:
                    running_cluster.append(clustername)
    cluster_to_destroy=[]
    for clustername in nodes_to_destroy_temp.keys():
        destroyEntireCluster=True
        if clustername in running_cluster:
            nodes_to_destroy[clustername]=nodes_to_destroy_temp[clustername]
            destroyEntireCluster=False
        else:
            for node in topology[clustername]:
                if not node in nodes_to_destroy_temp[clustername]:
                    nodes_to_destroy[clustername]=nodes_to_destroy_temp[clustername]
                    destroyEntireCluster=False
                    break
        if destroyEntireCluster:
            cluster_to_destroy.append([clustername])

    cluster_building=[]
    cluster_destroying=[]

    used_index={}
    for clusterName in os.listdir(clusters_path):
        if len(clusterName.split('-')) < 3:
            continue
        instance_keyword='-'.join(clusterName.split('-')[2:])
        clusterNumber=int(clusterName.split('-')[1])
        queue=clusterName.split('-')[0]
        instanceType=getInstanceType(config,queue,instance_keyword)
        if not queue in used_index.keys():
            used_index[queue]={}
        if not instanceType in used_index[queue].keys():
            used_index[queue][instanceType]=[]
        used_index[queue][instanceType].append(clusterNumber)

        if os.path.isfile(os.path.join(clusters_path,clusterName,'currently_building')):
            with open(os.path.join(clusters_path,clusterName,'currently_building'),'r') as f:
                line = f.read()
                nodes = line.split()[0]
                instance_type = line.split()[1]
                queue = line.split()[2]
            try:
                cluster_building.append([int(nodes),instance_type,queue])
                if queue in building_nodes.keys():
                    if instance_type in building_nodes[queue].keys():
                        building_nodes[queue][instance_type]+=int(nodes)
                    else:
                        building_nodes[queue][instance_type]=int(nodes)
                else:
                    building_nodes[queue]={instance_type:int(nodes)}
            except ValueError:
                print 'The cluster '+ clusterName + ' does not have a valid entry for \"currently_building\"'
                print 'Ignoring'
                continue
        if os.path.isfile(os.path.join(clusters_path,clusterName,'currently_destroying')):
            cluster_destroying.append(clusterName)
    return cluster_to_build,cluster_to_destroy,nodes_to_destroy,cluster_building,cluster_destroying,used_index,current_nodes,building_nodes

if os.path.isfile(lockfile):
    print("Lockfile "+lockfile + " is present, exiting")
    exit()
open(lockfile,'w').close()
try:
    path = os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0])))
    clusters_path = os.path.join(path,'clusters')
    config = getQueueConf(queues_conf_file)

    cluster_to_build,cluster_to_destroy,nodes_to_destroy,cluster_building,cluster_destroying,used_index,current_nodes,building_nodes=getstatus_slurm()

    print time.strftime("%Y-%m-%d %H:%M:%S")
    print cluster_to_build,'cluster_to_build'
    print cluster_to_destroy,'cluster_to_destroy'
    print nodes_to_destroy,'nodes_to_destroy'
    print cluster_building,'cluster_building'
    print cluster_destroying,'cluster_destroying'
    print current_nodes,'current_nodes'
    print building_nodes,'building_nodes'

    for i in cluster_building:
        for j in cluster_to_build:
            if i[0]==j[0] and i[1]==j[1] and i[2]==j[2]:
                cluster_to_build.remove(j)
                break
    for cluster in cluster_to_destroy:
        cluster_name=cluster[0]
        print "Deleting cluster "+cluster_name
        subprocess.Popen([script_path+'/delete_cluster.sh',cluster_name])
        time.sleep(1)

    for cluster_name in nodes_to_destroy.keys():
        print "Resizing cluster "+cluster_name
        initial_nodes=[]
        for node in nodes_to_destroy[cluster_name]:
            alt_names=subprocess.check_output(["cat /etc/hosts | grep "+node],shell=True)
            for alt_name in alt_names.split("\n")[0].split():
                if alt_name.startswith('inst-'):
                    initial_nodes.append(alt_name)
                    break
        subprocess.Popen([script_path+'/resize.sh','--cluster_name',cluster_name,'remove','--nodes']+initial_nodes)
        time.sleep(1)

    for index,cluster in enumerate(cluster_to_build):
        nodes=cluster[0]
        instance_type = cluster[1]
        queue=cluster[2]
        jobID=str(cluster[3])
        user=str(cluster[4])
        jobconfig=getJobConfig(config,queue,instance_type)
        limits=getQueueLimits(config,queue,instance_type)
        try:
            clusterCount=len(used_index[queue][instance_type])
        except:
            clusterCount=0
        if clusterCount>=limits["max_cluster_count"]:
            print "This would go over the number of running clusters, you have reached the max number of clusters"
            continue
        nextIndex=None
        if clusterCount==0:
            used_index[queue]={instance_type:[1]}
            nextIndex=1
        else:
            for i in range(1,10000):
                if not i in used_index[queue][instance_type]:
                    nextIndex=i
                    used_index[queue][instance_type].append(i)
                    break
        clusterName=queue+'-'+str(nextIndex)+'-'+jobconfig["instance_keyword"]
        if not queue in current_nodes.keys():
            current_nodes[queue]={instance_type:0}
        else:
            if not instance_type in current_nodes[queue].keys():
                current_nodes[queue][instance_type]=0
        if not queue in building_nodes.keys():
            building_nodes[queue]={instance_type:0}
        else:
            if not instance_type in building_nodes[queue].keys():
                building_nodes[queue][instance_type]=0
        if nodes > limits["max_cluster_size"]:
            print "Cluster "+clusterName+" won't be created, it would go over the total number of nodes per cluster limit"
        elif current_nodes[queue][instance_type] + building_nodes[queue][instance_type] + nodes > limits["max_number_nodes"]:
            print "Cluster "+clusterName+" won't be created, it would go over the total number of nodes limit"
        else:
            current_nodes[queue][instance_type]+=nodes
            clusterCount+=1
            print "Creating cluster "+clusterName+" with "+str(nodes)+" nodes"
            subprocess.Popen([script_path+'/create_cluster.sh',str(nodes),clusterName,instance_type,queue,jobID,user])
            time.sleep(5)

except Exception:
    traceback.print_exc()
os.remove(lockfile)