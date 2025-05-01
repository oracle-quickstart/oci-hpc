import pymysql
import sys
from mgmt_shared_logging import logger
import random
import string
import yaml
import copy
import re, os
import time
import base64

try:
    import oci
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    computeClient = oci.core.ComputeClient(config={}, signer=signer)
    ComputeClientCompositeOperations= oci.core.ComputeClientCompositeOperations(computeClient)
    computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=signer)
    ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(computeManagementClient)
    virtualNetworkClient = oci.core.VirtualNetworkClient(config={}, signer=signer)
    DNSClient = oci.dns.DnsClient(config={}, signer=signer)
    IdentityClient= oci.identity.IdentityClient(config={}, signer=signer)
    IdentityClientCompositeOperations= oci.identity.IdentityClientCompositeOperations(IdentityClient)
except ImportError:
    logger.error("oci API cannot be used. Exiting.")
    sys.exit(1)


db_host = "localhost"
db_user = "clusterUser"
db_pw = "Cluster1234!"
db_name = "clusterDB"

def query_db():
    try:
        # DB Connection Details
        connection = pymysql.connect(host=db_host, user=db_user, password=db_pw, database=db_name)
        logger.info("Database connection established successfully.")
    except pymysql.MySQLError as e:
        logger.error(f"Error connecting to the database: {e}")
        sys.exit(1)

    query = """
    SELECT *
    FROM nodes;
    """
    results = None
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query)
            results = cursor.fetchall()
            logger.info("Query executed successfully. Retrieved %d records.", len(results))
    except pymysql.MySQLError as e:
        logger.error(f"Database query failed: {e}")
    finally:
        connection.close()
        logger.info("Database connection closed.")
    return results

def reconfigure_controller(instance_ocid):
    try:
        connection = pymysql.connect(host=db_host, user=db_user, password=db_pw, database=db_name)
        logger.info("Database connection established successfully.")
    except pymysql.MySQLError as e:
        logger.error(f"Error connecting to the database: {e}")
        sys.exit(1)

    query = """
    UPDATE nodes
    SET controller_status = %s
    WHERE id = %s;
    """
    results = None
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, ("reconfiguring", instance_ocid))
            connection.commit()
            logger.info("Query executed successfully. Retrieved %d records.", len(results))
    except pymysql.MySQLError as e:
        logger.error(f"Database query failed: {e}")
    finally:
        connection.close()
        logger.info("Database connection closed.")

def list_custom_images(compartment_ocid):
    try:
        response = oci.pagination.list_call_get_all_results(computeClient.list_images,compartment_id=compartment_ocid)
 
        if response.data:
            logger.info(f"Custom Images in Compartment: {compartment_ocid}\n")
            custom_images = []
            for image in response.data:
                logger.info(image.display_name)
                custom_images.append(image)
            return custom_images
        else:
            logger.error(f"No custom images found in compartment {compartment_ocid}.")
            return []
    except oci.exceptions.ServiceError as e:
         logger.error(f"Error retrieving custom images: {compartment_ocid}")
         return [] 

def list_instance_configs(compartment_ocid):
    return computeManagementClient.list_instance_configurations(compartment_ocid).data

def list_instance_types():
    queues_file="/opt/oci-hpc/conf/queues.conf"
    instance_types=[]
    with open(queues_file, 'r') as file:
        data = yaml.safe_load(file)
    for partition in data["queues"]:
        for instance_type in partition["instance_types"]:
            deep_copied_dict = copy.deepcopy(instance_type)
            deep_copied_dict["partition"]=partition['name']
            instance_types.append(deep_copied_dict)
    return(instance_types)

def get_instance_type(instance_type_name):
    instance_types = list_instance_types()
    for instance_type in instance_types:
        if instance_type['name']==instance_type_name:
            return instance_type
    return None

def guess_availabilitydomain(compartment_ocid):
    ads=IdentityClient.list_availability_domains(compartment_ocid).data
    return [i.name for i in ads]

def list_subnets(compartment_ocid):
    return virtualNetworkClient.list_subnets(compartment_id=compartment_ocid).data