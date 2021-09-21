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
queues_conf_file = "/opt/oci-hpc/autoscaling/queues.conf"

# seconds for a cluster to stay alive
idle_time=600 #seconds

# Get the list of Jobs in all states
def getJobs():
    out = subprocess.Popen(['squeue','-O','STATE,JOBID,FEATURE:100,NUMNODES,Dependency,Partition,UserName'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()
    return stdout.split("\n")[1:]

def getClusters():
    out = subprocess.Popen(['sinfo','-r','-o','\"%T %E %D %N\"'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()
    return stdout.split("\n")[1:]
    
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
    cluster_start_time=datetime.datetime.strptime(stdout.split("\n")[0].split("=")[1],"%Y-%m-%dT%H:%M:%S")
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

def getstatus_slurm():
    cluster_to_build=[]

    for line in getJobs():
        if len(line.split())>3:
            if line.split()[0].strip() == 'PENDING' and 'null' in line.split()[4].strip():
                queue = line.split()[5].strip()
                user = line.split()[6].strip()
                features=line.split()[2].split('&')
                instanceType= None
                possible_types=[inst_type["name"] for inst_type in getQueue(config,queue)["instance_types"]]
                if len(features)>1:
                    if features[-2] in possible_types:
                        instanceType=feature
                        break
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
            clustername = '-'.join(node.split('[')[0].split('-')[:-2])
            queue = clustername.split('-')[0]
            instance_keyword='-'.join(clustername.split('-')[2:])
            instanceType=getInstanceType(config,queue,instance_keyword)
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
                if getIdleTime(node)<idle_time:
                    continue
                if isPermanent(config,queue,instanceType):
                    continue
                cluster_exists=False
                for cluster in cluster_to_destroy:
                    if cluster[0] == clustername:
                        cluster[1]=cluster[1]+int(line.split()[2])
                        cluster_exists=True
                if not cluster_exists:
                    cluster_to_destroy.append([clustername,int(line.split()[2]),queue,instanceType])
            elif line.split()[0] == '\"allocated':
                running_cluster.append(clustername)
    cluster_to_destroy_temp=copy.deepcopy(cluster_to_destroy)
    for cluster in cluster_to_destroy_temp:
        if cluster[0] in running_cluster:
            cluster_to_destroy.remove(cluster)
    cluster_building=[]
    cluster_destroying=[]

    available_names=getAllClusterNames(config)
    for clusterName in os.listdir(clusters_path):
        if len(clusterName.split('-')) < 3:
            continue
        instance_keyword='-'.join(clusterName.split('-')[2:])
        clusterNumber=int(clusterName.split('-')[1])
        queue=clusterName.split('-')[0]
        instanceType=getInstanceType(config,queue,instance_keyword)
        if queue == "inst": # For permanent nodes
            continue
        try:
            if clusterNumber in available_names[queue][instanceType]:
                available_names[queue][instanceType].remove(clusterNumber)
        except:
            print "Some nodes have different names than expected",queue,instanceType,available_names
            continue
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
    return cluster_to_build,cluster_to_destroy,cluster_building,cluster_destroying,available_names,current_nodes,building_nodes

if os.path.isfile(lockfile):
    print("Lockfile "+lockfile + " is present, exiting")
    exit()
open(lockfile,'w').close()
try:
    path = os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0])))
    clusters_path = os.path.join(path,'clusters')
    config = getQueueConf(queues_conf_file)

    cluster_to_build,cluster_to_destroy,cluster_building,cluster_destroying,available_names,current_nodes,building_nodes=getstatus_slurm()

    print time.strftime("%Y-%m-%d %H:%M:%S")
    print cluster_to_build,'cluster_to_build'
    print cluster_to_destroy,'cluster_to_destroy'
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
        subprocess.Popen([path+'/delete_cluster.sh',cluster_name])
        time.sleep(1)

    for index,cluster in enumerate(cluster_to_build):
        nodes=cluster[0]
        instance_type = cluster[1]
        queue=cluster[2]
        jobID=str(cluster[3])
        user=str(cluster[4])
        jobconfig=getJobConfig(config,queue,instance_type)
        if len(available_names[queue][instance_type]) == 0:
            print "No More available names, you have reached the max number of clusters"
            continue
        clusterName=queue+'-'+str(available_names[queue][instance_type][0])+'-'+jobconfig["instance_keyword"]
        available_names[queue][instance_type]=available_names[queue][instance_type][1:]
        limits=getQueueLimits(config,queue,instance_type)
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
        if current_nodes[queue][instance_type] + building_nodes[queue][instance_type] + nodes > limits["max_number_nodes"]:
            print "Cluster "+clusterName+" won't be created, it would go over the total number of nodes limit"
        else:
            current_nodes[queue][instance_type]+=nodes
            print "Creating cluster "+clusterName+"with "+str(nodes)+" nodes"
            subprocess.Popen([path+'/create_cluster.sh',str(nodes),clusterName,instance_type,queue,jobID,user])
            time.sleep(5)
    
except Exception:
    traceback.print_exc()
os.remove(lockfile)