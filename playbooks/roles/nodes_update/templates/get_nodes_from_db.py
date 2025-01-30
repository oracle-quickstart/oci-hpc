import pymysql
import json

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
print(json.dumps(results, indent=4))