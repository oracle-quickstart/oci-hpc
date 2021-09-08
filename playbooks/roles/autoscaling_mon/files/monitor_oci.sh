#!/usr/bin/python3

import datetime
import oci
import pytz
import mysql.connector
import os
import requests

def get_metadata():
    """ Make a request to metadata endpoint """
    headers = { 'Authorization' : 'Bearer Oracle' }
    metadata_url = "http://169.254.169.254/opc/"
    metadata_ver = "2"
    request_url = metadata_url + "v" + metadata_ver + "/instance/"
    return requests.get(request_url, headers=headers).json()

cli_node_ocid = get_metadata()["id"]
comp_ocid=get_metadata()["compartmentId"]

permanent_instances=[]

signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
computeClient = oci.core.ComputeClient(config={}, signer=signer)
computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=signer)
ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(computeManagementClient)

now_utc=datetime.datetime.now().astimezone(pytz.utc)
now_utc_TS=now_utc.strftime("%Y-%m-%d %H:%M:%S")

connection = mysql.connector.connect(host=os.environ['ENV_MYSQL_HOST'],database=os.environ['ENV_MYSQL_DATABASE_NAME'],user=os.environ['ENV_MYSQL_USER'],password=os.environ['ENV_MYSQL_PASS'])
cursor=connection.cursor()
cursor.execute("use cluster_log;")

cn_summaries = computeManagementClient.list_cluster_networks(comp_ocid).data
for cn_summary in cn_summaries:
    state=cn_summary.lifecycle_state
    createdBy=cn_summary.defined_tags['Oracle-Tag']['CreatedBy']
    createdOn=cn_summary.defined_tags['Oracle-Tag']['CreatedOn']
    createdOn_dt=datetime.datetime.strptime(createdOn,"%Y-%m-%dT%H:%M:%S.%fZ")
    seconds_created=(now_utc.replace(tzinfo=None)-createdOn_dt).total_seconds()
    if createdBy == cli_node_ocid :
        if cn_summary.id in permanent_instances:
            continue
        cursor.execute("SELECT state from clusters where cluster_OCID='"""+cn_summary.id+"""';""")
        result = cursor.fetchone()
        if result is None:
            if seconds_created > 3600 and state.lower() != 'terminated':
                mySql_insert_query="""INSERT INTO errors_timeserie (cluster_OCID,state,error_type,created_on_m) VALUES ('"""+cn_summary.id+"""','oci','The Cluster does not exist in the DB but is referenced in OCI Console.','"""+now_utc_TS+"""');"""
                print(mySql_insert_query)
                cursor.execute(mySql_insert_query)
        elif result[0] != state.lower() and result[0] != 'deleted' and  state.lower() != 'terminated':
            mySql_insert_query="""UPDATE clusters SET oci_state='"""+state.lower()+"""' where cluster_OCID='"""+cn_summary.id+"""';"""
            if state.lower() != "terminated":
                print(mySql_insert_query)
            cursor.execute(mySql_insert_query)
cursor.execute("SELECT cluster_OCID from clusters where oci_state <> 'terminated' and state='deleted';")
results = cursor.fetchall()
for i in results:
    try:
        if computeManagementClient.get_cluster_network(i[0]).data.lifecycle_state != 'TERMINATED':
            continue
    except:
        print('Cluster is unknown by OCI')
    mySql_insert_query="""UPDATE clusters SET oci_state='terminated' where cluster_OCID='"""+i[0]+"""';"""
    print(mySql_insert_query)
    cursor.execute(mySql_insert_query)
connection.commit()
cursor.close()
connection.close()