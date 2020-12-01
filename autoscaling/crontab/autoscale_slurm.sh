#!/bin/python

import subprocess
import datetime
import time
import sys, os
path = os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0])))
clusters_path = os.path.join(path,'clusters')
cluster_names_number=10
hpc_cluster_names_number=30
shapes={'VM.GPU2.1':'gpu2.1','BM.GPU2.2':'gpu2.2','VM.GPU3.1':'gpu3.1','VM.GPU3.2':'gpu3.2','VM.GPU3.4':'gpu3.4','BM.GPU3.8':'gpu3.8','BM.GPU4.8':'gpu4.8',\
    'VM.Standard2.1':'std21','VM.Standard2.2':'std22','VM.Standard2.4':'std24','VM.Standard2.8':'std28','VM.Standard2.16':'std216','VM.Standard2.24':'std224','BM.Standard2.52':'std52',
    'BM.Standard.E2.64':'amd264','BM.Standard.E3.128':'amd3128','BM.HPC2.36':'hpc'}

def getstatus_slurm():
    out = subprocess.Popen(['squeue','-O','STATE,JOBID,FEATURE:50,NUMNODES'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()

    cluster_to_build=[]
    for line in stdout.split("\n")[1:]:
        if len(line.split())>3:
            if line.split()[0].strip() == 'PENDING':
                features=line.split()[2].split('&')
                shape = "BM.HPC2.36"
                for feature in features:
                    if feature.startswith('VM') or feature.startswith('BM'):
                        shape=feature
                        break
                if shape == "BM.HPC2.36" or shape ==  "BM.GPU4.8":
                    CN = "true"
                else:
                    CN = "false"
                cluster_to_build.append([int(line.split()[3]),int(line.split()[1]),shape,CN])

    cluster_to_destroy=[]
    out = subprocess.Popen(['sinfo','-o','\"%T %E %N\"'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()
    for line in stdout.split("\n")[1:]:
        if len(line.split()) == 0:
            break
        if line.split()[0] == '\"idle':
            nodes=line.split()[-1].split(',')
            clusters = []
            for node in nodes:
                clustername = '-'.join(node.split('-')[0:3])
                if not clustername in clusters:
                    clusters.append(clustername)
                    cluster_to_destroy.append(clustername)

    cluster_building=[]
    cluster_destroying=[]
    available_names = {}
    for shape in shapes.keys():
        available_names[shapes[shape]] = ["cluster-"+str(i) for i in range(1,cluster_names_number+1)]
    available_names['hpc']=["cluster-"+str(i) for i in range(1,hpc_cluster_names_number+1)]
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
            except ValueError:
                print 'The cluster '+ clusterName + ' does not have a valid entry for \"currently_building\"'
                print 'Ignoring'
                continue
        if os.path.isfile(os.path.join(clusters_path,clusterName,'currently_destroying')):
            cluster_destroying.append(clusterName)
    return cluster_to_build,cluster_to_destroy,cluster_building,cluster_destroying,available_names

cluster_to_build,cluster_to_destroy,cluster_building,cluster_destroying,available_names=getstatus_slurm()

print time.strftime("%Y-%m-%d %H:%M:%S")
print cluster_to_build,'cluster_to_build'
print cluster_to_destroy,'cluster_to_destroy'
print cluster_building,'cluster_building'
print cluster_destroying,'cluster_destroying'


for i in cluster_building:
    for j in cluster_to_build:
        if i[0]==j[0] and i[1]==j[2] and i[2]==j[3]:
            cluster_to_build.remove(j)
            break
for cluster in cluster_to_build:
    shape = cluster[2]
    keyworkShape=shapes[shape]
    clusterName=available_names[keyworkShape][0]+'-'+keyworkShape
    subprocess.Popen([path+'/create_cluster.sh',str(cluster[0]),clusterName,cluster[2],cluster[3]])
for cluster in cluster_to_destroy:
    subprocess.Popen([path+'/delete_cluster.sh',str(cluster)])