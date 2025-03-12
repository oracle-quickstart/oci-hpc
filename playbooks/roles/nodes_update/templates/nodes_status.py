import pymysql
import json
from ClusterShell.NodeSet import NodeSet

#DB Connection Details
db_host="localhost"
db_user="clusterUser"
db_pw="Cluster1234!"
db_name="clusterDB"

connection = pymysql.connect(host=db_host, user=db_user, password=db_pw, database=db_name)

query = """
SELECT * 
FROM nodes
WHERE controller_name = %s;
"""


params = ("{{controller_hostname}}",)

try:
    with connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute(query, params)
        results = cursor.fetchall()
finally:
    connection.close()


configured_nodes=[]
waiting_for_compute=[]
terminating=[]
starting=[]

compute=[i for i in results if i["role"]=="compute"]
for i in compute:
    if i["controller_status"] == "configured" and i["compute_status"] == "configured": 
       configured_nodes.append(i)
    elif i["controller_status"] == "configured" and i["compute_status"] == "configuring":
       waiting_for_compute.append(i)
    elif i["controller_status"] == "terminating":
       terminating.append(i)
    elif i["controller_status"] == "waiting_for_info":
       starting.append(i)

print("Counts:")
print("Configured_nodes:" + str(len(configured_nodes))+"    Configuring_nodes:"+str(len(waiting_for_compute))+"     Starting_nodes:"+str(len(starting))+"     Terminating_nodes:"+str(len(terminating)))
       

print("Details:")
print("Configured_nodes:" + str(NodeSet(','.join([ i["hostname"] for i in configured_nodes]))))
print("Configuring_nodes:"+ str(NodeSet(','.join([ i["hostname"] for i in waiting_for_compute]))))
print("Terminating_nodes:"+ str(NodeSet(','.join([ i["hostname"] for i in terminating]))))
print("Starting_nodes:"+ ','.join([ i["ip_address"] for i in starting]))
