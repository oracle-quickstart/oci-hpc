#!/bin/python
import subprocess
import datetime
import time
import sys, os
import traceback
lockfile = "/tmp/autoscaling_lock"
idle_time=600 #seconds

def getJobs():
    out = subprocess.Popen(['squeue','-O','STATE,JOBID,FEATURE:50,NUMNODES,Dependency'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
        return ( datetime.datetime.now() - last_end_time ).total_seconds()
    except:
        out = subprocess.Popen(["scontrol show node "+node+" | grep SlurmdStartTime | awk '{print $2}'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True)
        stdout,stderr = out.communicate()
        cluster_start_time=datetime.datetime.strptime(stdout.split("\n")[0].split("=")[1],"%Y-%m-%dT%H:%M:%S")
        return ( datetime.datetime.now() - cluster_start_time ).total_seconds()

if os.path.isfile(lockfile):
    print("Lockfile "+lockfile + " is present, exiting")
    exit()
open(lockfile,'w').close()
try:
    path = os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0])))
    clusters_path = os.path.join(path,'clusters')
    max_number_nodes=20
    min_number_nodes=0

    cluster_names_number=20
    hpc_cluster_names_number=50
    shapes={}
    shapes['VM.GPU2.1']='gpu21'
    shapes['BM.GPU2.2']='gpu22'
    for i in 1,2,4:
        shapes['VM.GPU3.'+str(i)]='gpu3'+str(i)
    shapes['BM.GPU3.8']='gpu38'
    shapes['BM.GPU4.8']='gpu48'
    for i in 1,2,4,8,16,24:
        shapes['VM.Standard2.'+str(i)]='std2'+str(i)
    shapes['BM.Standard2.52']='std252'
    for i in 1,2,4,8,16,32:
        shapes['VM.Standard.E2.'+str(i)]='amd2'+str(i)
    shapes['BM.Standard.E2.64']='amd264'
    for i in range(1,65):
        shapes['VM.Standard.E3.'+str(i)]='amd3'+str(i)
        shapes['VM.Standard.E4.'+str(i)]='amd4'+str(i)
    shapes['BM.Standard.E3.128']='amd3128'
    shapes['BM.Standard.E3.128']='amd4128'
    shapes['BM.HPC2.36']='hpc'
    shapes['BM.Optimized3.36']='hpc2'

    def getstatus_slurm():
        cluster_to_build=[]
        for line in getJobs():
            if len(line.split())>3:
                if line.split()[0].strip() == 'PENDING' and 'null' in line.split()[-1].strip():
                    features=line.split()[2].split('&')
                    shape = "BM.HPC2.36"
                    for feature in features:
                        if feature.startswith('VM') or feature.startswith('BM'):
                            shape=feature
                            break
                    if shape == "BM.HPC2.36" or shape ==  "BM.GPU4.8" or shape ==  "BM.Optimized3.36":
                        CN = "true"
                    else:
                        CN = "false"
                    cluster_to_build.append([int(line.split()[3]),int(line.split()[1]),shape,CN])

        cluster_to_destroy=[]
        current_nodes=0
        building_nodes=0
        running_cluster=[]

        for line in getClusters():
            if len(line.split()) == 0:
                break
            current_nodes+=int(line.split()[2])
            if line.split()[0] == '\"idle':
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
                    clustername = '-'.join(node.split('-')[0:3])
                    if not os.path.isdir(os.path.join(clusters_path,clustername)):
                        continue
                    if getIdleTime(node)<idle_time:
                        continue
                    cluster_exists=False
                    for cluster in cluster_to_destroy:
                        if cluster[0] == clustername:
                            cluster[1]=cluster[1]+int(line.split()[2])
                            cluster_exists=True
                    if not cluster_exists:
                        cluster_to_destroy.append([clustername,int(line.split()[2])])
            elif line.split()[0] == '\"allocated':
                nodes=line.split()[-1].split(',')
                clusters = []
                for node in nodes:
                    clustername = '-'.join(node.split('-')[0:3])
                    running_cluster.append(clustername)
        for cluster in cluster_to_destroy:
            if cluster[0] in running_cluster:
                cluster_to_destroy.remove(cluster)
        cluster_building=[]
        cluster_destroying=[]
        available_names = {}
        for shape in shapes.keys():
            available_names[shapes[shape]] = ["cluster-"+str(i) for i in range(1,cluster_names_number+1)]
        available_names['hpc']=["cluster-"+str(i) for i in range(1,hpc_cluster_names_number+1)]
        available_names['hpc2']=["cluster-"+str(i) for i in range(1,hpc_cluster_names_number+1)]

        for clusterName in os.listdir(clusters_path):
            clusterType=clusterName.split('-')[-1]
            clusterNumber='-'.join(clusterName.split('-')[:2])
            try:
                if clusterNumber in available_names[clusterType]:
                    available_names[clusterType].remove(clusterNumber)
            except:
                continue
            if os.path.isfile(os.path.join(clusters_path,clusterName,'currently_building')):
                with open(os.path.join(clusters_path,clusterName,'currently_building'),'r') as f:
                    line = f.read()
                    nodes = line.split()[0]
                    shape = line.split()[1]
                    CN = line.split()[2]
                try:
                    cluster_building.append([int(nodes),shape,CN])
                    building_nodes+=int(nodes)
                except ValueError:
                    print 'The cluster '+ clusterName + ' does not have a valid entry for \"currently_building\"'
                    print 'Ignoring'
                    continue
            if os.path.isfile(os.path.join(clusters_path,clusterName,'currently_destroying')):
                cluster_destroying.append(clusterName)
        return cluster_to_build,cluster_to_destroy,cluster_building,cluster_destroying,available_names,current_nodes,building_nodes

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
            if i[0]==j[0] and i[1]==j[2] and i[2]==j[3]:
                cluster_to_build.remove(j)
                break
    for index,cluster in enumerate(cluster_to_build):
        shape = cluster[2]
        keyworkShape=shapes[shape]
        clusterName=available_names[keyworkShape][index]+'-'+keyworkShape
        if current_nodes + building_nodes + cluster[0]> max_number_nodes:
            print "Cluster "+clusterName+" won't be created, it would go over the total number of nodes limit"
        else:
            current_nodes+=cluster[0]
            print "Creating cluster "+clusterName+"with "+str(cluster[0])+" nodes"
            subprocess.Popen([path+'/create_cluster.sh',str(cluster[0]),clusterName,cluster[2],cluster[3]])
            time.sleep(5)
    for cluster in cluster_to_destroy:
        if current_nodes - cluster[1] < min_number_nodes:
            print "Cluster "+cluster[0]+" won't be deleted, it would go under the minimum number of nodes limit"
        else:
            print "Deleting cluster "+cluster[0]
            subprocess.Popen([path+'/delete_cluster.sh',str(cluster[0])])
except Exception:
    traceback.print_exc()
os.remove(lockfile)