#!/bin/python

import subprocess
import datetime
import time
import sys, os
path = os.path.dirname(os.path.dirname(os.path.realpath(sys.argv[0])))
clusters_path = os.path.join(path,'clusters')
cluster_names_number=10

def getstatus_slurm():
    out = subprocess.Popen(['squeue'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()

    cluster_to_build=[]
    for line in stdout.split("\n")[1:]:
        if len(line.split())>6:
            if line.split()[4].strip() == 'PD':
                cluster_to_build.append([int(line.split()[6]),line.split()[0]])

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
                clustername = '-'.join(node.split('-')[0:2])
                if not clustername in clusters:
                    clusters.append(clustername)
                    cluster_to_destroy.append(clustername)

    cluster_building=[]
    cluster_destroying=[]
    available_names=["cluster-"+str(i) for i in range(1,cluster_names_number+1)]
    for clusterName in os.listdir(clusters_path):
        if clusterName in available_names:
            available_names.remove(clusterName)
        if os.path.isfile(os.path.join(clusters_path,clusterName,'currently_building')):
            with open(os.path.join(clusters_path,clusterName,'currently_building'),'r') as f:
                nodes = f.read()
            try:
                cluster_building.append(int(nodes))
            except ValueError:
                print 'The cluster '+ clusterName + ' does not have a valid entry for \"currently_building\"'
                print 'Ignoring'
                continue
        if os.path.isfile(os.path.join(clusters_path,clusterName,'currently_destroying')):
            cluster_destroying.append(clusterName)
    return cluster_to_build,cluster_to_destroy,cluster_building,cluster_destroying,available_names

cluster_to_build,cluster_to_destroy,cluster_building,cluster_destroying,available_names=getstatus_slurm()

print cluster_to_build,'cluster_to_build'
print cluster_to_destroy,'cluster_to_destroy'
print cluster_building,'cluster_building'
print cluster_destroying,'cluster_destroying'

for i in cluster_building:
    for j in cluster_to_build:
        if i==j[0]:
            cluster_to_build.remove(j)
            break

for index,cluster in enumerate(cluster_to_build):
    subprocess.Popen([path+'/create_cluster.sh',str(cluster[0]),available_names[index]])
for cluster in cluster_to_destroy:
    subprocess.Popen([path+'/delete_cluster.sh',str(cluster)])