#!/usr/bin/python3

# Pre Requisite: sudo pip3 install mysql-connector-python

import subprocess
import mysql.connector
import datetime
import pytz
import os

# Get the list of Jobs in all states
def getAllJobs():
    delay="2days"
    out = subprocess.Popen(['sacct -S now-'+delay+" -o JobID,Partition,State,Submit,Start,End,NNodes,Ncpus,NodeList -X -n --parsable2"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, encoding='utf8', universal_newlines=True)
    stdout,stderr = out.communicate()
    return stdout.split("\n")

# Get the list of all nodes registered in Slurm
def getClusters():
    out = subprocess.Popen(['sinfo -h -N -r -O NodeList:50,CPUsState,StateLong,PartitionName'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, encoding='utf8', universal_newlines=True)
    stdout,stderr = out.communicate()
    return stdout.split("\n")

def getNodesFromQueuedJob(jobID):
    out = subprocess.Popen(['squeue -j '+jobID+' -o %D -h'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,encoding='utf8',universal_newlines=True)
    stdout,stderr = out.communicate()
    return stdout.split("\n")[0]

def getListOfNodes(nodelist):
    out = subprocess.Popen(['scontrol show hostnames '+' '.join(nodelist)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,encoding='utf8',universal_newlines=True)
    stdout,stderr = out.communicate()
    return stdout.split("\n")

def getOrigHostname(hostname):
    output = subprocess.check_output("cat /etc/hosts | grep \" "+hostname+" \" | awk '{print $4}'", shell=True,encoding='utf8',universal_newlines=True)
    return output.split("\n")[0]

def getAllHosts(rangedHost):
    output = subprocess.check_output("scontrol show hostname "+rangedHost, shell=True,encoding='utf8',universal_newlines=True)
    return output.split("\n")

def getTopology(clusterName):
    out = subprocess.Popen(['scontrol','show','topology',clusterName], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    stdout,stderr = out.communicate()
    for item in stdout.strip().split():
        if item.startswith("Nodes="):
            nodes_condensed=item.split("Nodes=")[1]
            out2 = subprocess.Popen(['scontrol','show','hostname',nodes_condensed], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            stdout2,stderr2 = out2.communicate()    
            print(stdout2.strip().split())
            return stdout2.strip().split()
    return []


def getClusterName(node):
    out = subprocess.Popen(['scontrol','show','topology',node], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    stdout,stderr = out.communicate()
    clusterName = None
    try:
        if len(stdout.split('\n')) > 2:
            for output in stdout.split('\n')[:-1]:
                if "Switches=" in output:
                    clusterName=output.split()[0].split('SwitchName=')[1]
                    break
                elif "SwitchName=inactive-" in output:
                    continue
                else:
                    clusterName=output.split()[0].split('SwitchName=')[1]
        elif len(stdout.split('\n')) == 2:
            clusterName=stdout.split('\n')[0].split()[0].split('SwitchName=')[1]
        if clusterName.startswith("inactive-"):
            return "NOCLUSTERFOUND"
    except: 
        print('No ClusterName could be found for '+node)
        return "NOCLUSTERFOUND"
    return clusterName

#def getCPUsDetails(job):
#    out = subprocess.Popen(['scontrol','show','job',job,'-d','|','grep','\" Nodes=.*CPU_IDs\"'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,encoding='utf8')
#    stdout,stderr = out.communicate()
#    cpuIDs=stdout.split()[1].replace("CPU_IDs=","")
#    return cpuIDs

connection = mysql.connector.connect(host=os.environ['ENV_MYSQL_HOST'],database=os.environ['ENV_MYSQL_DATABASE_NAME'],user=os.environ['ENV_MYSQL_USER'],password=os.environ['ENV_MYSQL_PASS'])
cursor=connection.cursor()
cursor.execute("use cluster_log;")
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
now_utc=datetime.datetime.now().astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")

for line in getAllJobs():
    splittedLine=line.split('|')
    if len(splittedLine) == 1:
        continue
    jobID=splittedLine[0]
    queue=splittedLine[1]
    state=splittedLine[2]
    submit=splittedLine[3]
    start=splittedLine[4]
    end=splittedLine[5]
    nodes=splittedLine[6]
    cpus=splittedLine[7]
    nodelist=splittedLine[8]
    if not 'None assigned' in nodelist:
        nodenames=getAllHosts(nodelist)
    else:
        nodenames=[]

    if submit != "Unknown":
        submit_datetime=datetime.datetime.strptime(submit,"%Y-%m-%dT%H:%M:%S")
        submit_TS=submit_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")

    if start != "Unknown":
        start_datetime=datetime.datetime.strptime(start,"%Y-%m-%dT%H:%M:%S")
        start_TS=start_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")

    if end != "Unknown":
        end_datetime=datetime.datetime.strptime(end,"%Y-%m-%dT%H:%M:%S")
        end_TS=end_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")

    mySql_insert_query=None
    cursor.execute("SELECT state from jobs where job_id='"+jobID+"' ;")
    result = cursor.fetchone()
    if result is None:
        current_sql_state=None
        if start == "Unknown":
            nodes=getNodesFromQueuedJob(jobID)
            # added "from dual" as mariadb (for Ubuntu) requires it
            mySql_insert_query="""insert into jobs (job_id,cpus,nodes,submitted,state,class_name) Select '"""+jobID+"""','"""+cpus+"""','"""+nodes+"""','"""+submit_TS+"""','queued','"""+queue+"""' from dual Where not exists(select * from jobs where job_id='"""+jobID+"""') ;"""
        elif end == "Unknown":
            clustername = getClusterName(nodenames[0])
            # added "from dual" as mariadb (for Ubuntu) requires it
            mySql_insert_query="""insert into jobs (job_id,cpus,nodes,submitted,started,queue_time,state,class_name,cluster_name) Select '"""+jobID+"""','"""+cpus+"""','"""+nodes+"""','"""+submit_TS+"""','"""+start_TS+"""','"""+str(start_datetime-submit_datetime).split('.')[0]+"""','running','"""+queue+"""','"""+clustername+"""' from dual Where not exists(select * from jobs where job_id='"""+jobID+"""') ;"""
        else:
            if 'failed' in state.lower():
                db_state = 'failed'
            elif 'cancelled' in state.lower():
                db_state = 'cancelled'
            elif 'completed' in state.lower():
                db_state = 'done'
            else:
                print(state+" was not failed, cancelled or completed")
                continue
            try:
                clustername = getClusterName(nodenames[0])
            except:
                clustername= ''
            # added "from dual" as mariadb (for Ubuntu) requires it
            mySql_insert_query="""insert into jobs (job_id,cpus,nodes,submitted,started,finished,queue_time,run_time,state,class_name,cluster_name) Select '"""+jobID+"""','"""+cpus+"""','"""+nodes+"""','"""+submit_TS+"""','"""+start_TS+"""','"""+end_TS+"""','"""+str(start_datetime-submit_datetime).split('.')[0]+"""','"""+str(end_datetime-start_datetime).split('.')[0]+"""','"""+db_state+"""','"""+queue+"""','"""+clustername+"""' from dual Where not exists(select * from jobs where job_id='"""+jobID+"""') ;"""
    else:
        current_sql_state = result[0]
        if start == "Unknown":
            continue
        elif end == "Unknown":
            if current_sql_state == 'queued':
                mySql_insert_query="""UPDATE jobs SET started='"""+start_TS+"""',queue_time='"""+str(start_datetime-submit_datetime).split('.')[0]+"""',state='running' where job_id='"""+jobID+"""';"""
        else:
            if current_sql_state == 'queued' or current_sql_state == 'running':
                if 'failed' in state.lower():
                    db_state = 'failed'
                elif 'cancelled' in state.lower():
                    db_state = 'cancelled'
                elif 'completed' in state.lower():
                    db_state = 'done'
                else:
                    print(state+" was not failed, cancelled or completed")
                    continue
                mySql_insert_query="""UPDATE jobs SET started='"""+start_TS+"""',finished='"""+end_TS+"""',queue_time='"""+str(start_datetime-submit_datetime).split('.')[0]+"""',run_time='"""+str(end_datetime-start_datetime).split('.')[0]+"""',state='"""+db_state+"""' where job_id='"""+jobID+"""';"""
    if not mySql_insert_query is None:
        print(mySql_insert_query)
        cursor.execute(mySql_insert_query)
    for node_name in getListOfNodes(nodelist):
        cpus_per_node = str(int(float(cpus)/float(nodes)))
        mySql_insert_query="""INSERT INTO jobs_timeserie (node_id,job_id,created_on_m,used_cpus,class_name) select id,'"""+jobID+"""','"""+now_utc+"""',"""+cpus_per_node+""",'"""+queue+"""' from nodes where hostname='"""+node_name+"""';"""
    cursor.execute(mySql_insert_query)

for line in getClusters():
    if len(line.split()) == 0:
        continue
    nodename=line.split()[0]
    total_used_cpus=line.split()[1].split('/')[0]
    actual_state=line.split()[2]
    queue=line.split()[3]
    alloc_states=['alloc','allocated','comp','completing','drain','draining','drained','mix','mixed']
    if actual_state.lower() in alloc_states:
        state='busy'
    else:
        state='idle'
    hostname_orig=getOrigHostname(nodename)
    mySql_insert_query="""INSERT INTO nodes_timeserie (node_id,state_m,created_on_m,used_cpus,class_name) select id,'"""+state+"""','"""+now_utc+"""','"""+total_used_cpus+"""','"""+queue+"""' from nodes where hostname='"""+hostname_orig+"""';"""
    cursor.execute(mySql_insert_query)
    mySql_insert_query="""UPDATE nodes SET sched_state='"""+state+"""' WHERE hostname='"""+hostname_orig+"""';"""
    cursor.execute(mySql_insert_query)
mySql_insert_query="""insert into nodes_timeserie (node_id,state_m,created_on_m,class_name) select id,state,'"""+now_utc+"""','class_name' from nodes where state='provisioning';"""
cursor.execute(mySql_insert_query)

connection.commit()
cursor.close()
connection.close()