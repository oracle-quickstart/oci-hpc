#!/usr/bin/python3

# Pre Requisite: sudo pip3 install mysql-connector-python

import subprocess
import mysql.connector
import datetime
import pytz
import os

# Get the list of Jobs in all states
def getJobs():
    out = subprocess.Popen(['squeue','-O','STATE,JOBID,FEATURE:100,NUMNODES,Dependency'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    stdout,stderr = out.communicate()
    return stdout.split("\n")[1:]

# Get the list of Finished Jobs in all states
def getOldJobs():
    out = subprocess.Popen(['/opt/pbs/bin/qstat','-H'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,encoding='utf8')
    stdout,stderr = out.communicate()
    if len(stdout.split("\n")) < 4 :
        return []
    else :
        return stdout.split("\n")[2:]

# Get the details of a job in the queue.
def getOldJobDetails(jobID):
    out = subprocess.Popen(['/opt/pbs/bin/qstat','-fxw','-Fdsv',jobID], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,encoding='utf8')
    stdout,stderr = out.communicate()
    return stdout.split('|')

# Get the details of a job in the queue.
def getJobDetails(jobID):
    out = subprocess.Popen(['/opt/pbs/bin/qstat','-f','-Fdsv',jobID], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,encoding='utf8')
    stdout,stderr = out.communicate()
    return stdout.split('|')

# Get the details of a job in the queue.
def getJobDetails(jobID):
    out = subprocess.Popen(['/opt/pbs/bin/qstat','-f','-Fdsv',jobID], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,encoding='utf8')
    stdout,stderr = out.communicate()
    return stdout.split('|')

# Get the list of all nodes registered in PBS
def getClusters():
    out = subprocess.Popen(['/opt/pbs/bin/pbsnodes','-aSL'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,encoding='utf8')
    stdout,stderr = out.communicate()
    return stdout.split("\n")[2:]

# Get the details of a node
def getClustersDetails(node):
    out = subprocess.Popen(['/opt/pbs/bin/pbsnodes','-Fdsv',node], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,encoding='utf8')
    stdout,stderr = out.communicate()
    return stdout.split('|')

# Get the last time a node state was changed.
def getIdleTime(node):
    out = subprocess.Popen(["/opt/pbs/bin/pbsnodes -v "+node+" | grep last_state_change_time"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,encoding='utf8')
    stdout,stderr = out.communicate()
    last_end_time = datetime.datetime.strptime(stdout.split("=")[1].strip(),"%a %b %d %H:%M:%S %Y")
    return ( datetime.datetime.now() - last_end_time ).total_seconds()

connection = mysql.connector.connect(host=os.environ['ENV_MYSQL_HOST'],database=os.environ['ENV_MYSQL_DATABASE_NAME'],user=os.environ['ENV_MYSQL_USER'],password=os.environ['ENV_MYSQL_PASS'])
cursor=connection.cursor()
cursor.execute("use cluster_log;")
now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
now_utc=datetime.datetime.now().astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")

for line in getJobs():

    cluster_name=None
    mySql_insert_query=None
    cursor.execute("SELECT state from jobs where job_id='"+jobName+"' ;")
    result = cursor.fetchone()
    if result is None:
        current_sql_state=None
    else:
        current_sql_state = result[0]
    if len(line.split())>3:
        status=line.split()[0].strip()
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

    for element in getJobDetails(jobID):
        # If shape is defined, change the shape from BM.HPC2.36
        if 'Resource_List.select' in element:
            element.split(':')
            for i in element:
                if i.split('=')[0] == 'shape':
                    shape=i.split('=')[1]
        # Grab the job queue
        if element.split('=')[0] == 'queue':
            queue=element.split('=')[1]
        # Grab the number of cpus requested for the job
        if element.split('=')[0] == 'Resource_List.ncpus':
            cpus=int(element.split('=')[1])
        # Grab the job priority
        if element.split('=')[0] == 'Priority':
            priority=int(element.split('=')[1])
        if element.split('=')[0] == 'exec_host':
            cluster_name='-'.join(element.split('=')[1].split('/')[0].split('-')[2:])
            print(cluster_name)
        # Grab the job etime to get how long the job has been queued
        if element.split('=')[0] == 'etime':
            etime=element.split('=')[1]
            etime_datetime=datetime.datetime.strptime(etime,"%a %b %d %H:%M:%S %Y")
            etime_TS=etime_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        if element.split('=')[0] == 'stime':
            stime=element.split('=')[1]
            stime_datetime=datetime.datetime.strptime(stime,"%a %b %d %H:%M:%S %Y")
            stime_TS=stime_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        if shape == "BM.HPC2.36" or shape ==  "BM.GPU4.8":
            CN = "true"
        else:
            CN = "false"
    if current_sql_state is None :
        if stime=="" :
            mySql_insert_query="""insert into jobs (job_id,cpus,nodes,submitted,state,class_name) Select '"""+jobName+"""','"""+str(cpus)+"""','"""+str(nodes)+"""','"""+etime_TS+"""','queued','"""+queue+"""' Where not exists(select * from jobs where job_id='"""+jobName+"""') ;"""
        else:
            mySql_insert_query="""insert into jobs (job_id,cpus,nodes,submitted,started,queue_time,state,class_name,cluster_name) Select '"""+jobName+"""','"""+str(cpus)+"""','"""+str(nodes)+"""','"""+etime_TS+"""','"""+stime_TS+"""','"""+str(stime_datetime-etime_datetime).split('.')[0]+"""','running','"""+queue+"""','"""+cluster_name+"""' Where not exists(select * from jobs where job_id='"""+jobName+"""') ;"""
    else :
        if current_sql_state == 'queued' and stime!= "":
            mySql_insert_query="""UPDATE jobs SET started='"""+stime_TS+"""',queue_time='"""+str(stime_datetime-etime_datetime).split('.')[0]+"""',state='running' where job_id='"""+jobName+"""';"""
    if not mySql_insert_query is None:
        cursor.execute(mySql_insert_query)

for line in getOldJobs():
    if len(line.split()) < 10:
        continue
    elif line.startswith("Job ID") or line.startswith("---"):
            continue
    jobID = line.split()[0].split('.')[0]
    jobName = line.split()[0]

    #mySql_query="""select * from clusters where id='"""+jobName+"""';"""
    #result=cursor.fetchall()
    #if len(result):
    #    break
    nodes = int(line.split()[5])
    shape = "BM.HPC2.36"
    queue = ""
    cpus = 0
    priority = 0
    etime=""
    mtime=""
    stime=""
    cursor.execute("SELECT state from jobs where job_id='"+jobName+"' ;")
    result = cursor.fetchone()
    if result is None:
        current_sql_state=None
    else:
        current_sql_state = result[0]
    if current_sql_state == "done" or current_sql_state == "failed":
        continue
    for element in getOldJobDetails(jobID):
        # If shape is defined, change the shape from BM.HPC2.36
        if 'Resource_List.select' in element:
            element.split(':')
            for i in element:
                if i.split('=')[0] == 'shape':
                    shape=i.split('=')[1]
        # Grab the job queue
        if element.split('=')[0] == 'queue':
            queue=element.split('=')[1]
        # Grab the number of cpus requested for the job
        if element.split('=')[0] == 'Resource_List.ncpus':
            cpus=int(element.split('=')[1])
        # Grab the job priority
        if element.split('=')[0] == 'Priority':
            priority=int(element.split('=')[1])
        # Grab the job etime to get how long the job has been queued
        if element.split('=')[0] == 'etime':
            etime=element.split('=')[1]
            etime_datetime=datetime.datetime.strptime(etime,"%a %b %d %H:%M:%S %Y")
            etime_TS=etime_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        if element.split('=')[0] == 'stime':
            stime=element.split('=')[1]
            stime_datetime=datetime.datetime.strptime(stime,"%a %b %d %H:%M:%S %Y")
            stime_TS=stime_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        if element.split('=')[0] == 'mtime':
            mtime=element.split('=')[1]
            mtime_datetime=datetime.datetime.strptime(mtime,"%a %b %d %H:%M:%S %Y")
            mtime_TS=mtime_datetime.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S")
        if shape == "BM.HPC2.36" or shape ==  "BM.GPU4.8":
            CN = "true"
        else:
            CN = "false"
    if current_sql_state is None:
        if stime=="" or etime=="" or mtime=="" :
            mySql_insert_query="""insert into jobs (job_id,cpus,nodes,submitted,state,class_name) Select '"""+jobName+"""','"""+str(cpus)+"""','"""+str(nodes)+"""','"""+etime_TS+"""','failed','"""+queue+"""' Where not exists(select * from jobs where job_id='"""+jobName+"""') ;"""
        else:
            mySql_insert_query="""insert into jobs (job_id,cpus,nodes,submitted,started,finished,queue_time,run_time,state,class_name) Select '"""+jobName+"""','"""+str(cpus)+"""','"""+str(nodes)+"""','"""+etime_TS+"""','"""+stime_TS+"""','"""+mtime_TS+"""','"""+str(stime_datetime-etime_datetime).split('.')[0]+"""','"""+str(mtime_datetime-stime_datetime).split('.')[0]+"""','done','"""+queue+"""' Where not exists(select * from jobs where job_id='"""+jobName+"""') ;"""
    else:
        if stime=="" or etime=="" or mtime=="" :
            mySql_insert_query="""UPDATE jobs SET submitted='"""+etime_TS+"""',state='failed' where job_id='"""+jobName+"""';"""
        else:
            mySql_insert_query="""UPDATE jobs SET submitted='"""+etime_TS+"""',started='"""+stime_TS+"""',finished='"""+mtime_TS+"""',queue_time='"""+str(stime_datetime-etime_datetime).split('.')[0]+"""',run_time='"""+str(mtime_datetime-stime_datetime).split('.')[0]+"""',state='done' where job_id='"""+jobName+"""';"""
    cursor.execute(mySql_insert_query)

for line in getClusters():
    if len(line.split()) == 0:
        break
    node=line.split()[0]
    clustername = '-'.join(node.split('-')[2:])
    jobs={}
    state="idle"
    total_used_cpus=0
    queue="NULL"
    for element in getClustersDetails(node):
        if element.startswith("jobs="):
            state="busy"
            job_per_core=element.split('=')[1].split(",")
            total_used_cpus=len(job_per_core)
            for i in job_per_core:
                job=i.split("/")[0]
                if not job in jobs:
                    jobs[job]=1
                else:
                    jobs[job]+=1
        if element.split('=')[0] == 'queue':
            queue=element.split('=')[1]
    mySql_insert_query="""INSERT INTO nodes_timeserie (node_id,state_m,created_on_m,used_cpus) select id,'"""+state+"""','"""+now_utc+"""',"""+str(total_used_cpus)+""" from nodes where hostname='"""+node+"""';"""
    cursor.execute(mySql_insert_query)
    mySql_insert_query="""UPDATE nodes SET PBS_state='"""+state+"""' WHERE hostname='"""+node+"""';"""
    cursor.execute(mySql_insert_query)
    for job in jobs.keys():
        mySql_insert_query="""INSERT INTO jobs_timeserie (node_id,job_id,created_on_m,used_cpus) select id,'"""+job+"""','"""+now_utc+"""',"""+str(jobs[job])+""" from nodes where hostname='"""+node+"""';"""
        cursor.execute(mySql_insert_query)
mySql_insert_query="""insert into nodes_timeserie (node_id,state_m,created_on_m) select id,state,'"""+now_utc+"""' from nodes where state='provisioning';"""
cursor.execute(mySql_insert_query)


connection.commit()
cursor.close()
connection.close()