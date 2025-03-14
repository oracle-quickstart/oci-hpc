import pymysql
from ClusterShell.NodeSet import NodeSet
import sys
import logging
import argparse
from datetime import datetime, timedelta, timezone
import time

controller_hostname = "{{controller_hostname}}"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Argument parsing
parser = argparse.ArgumentParser(description="Process node list and flags.")
parser.add_argument("--nodes", type=str, help="Comma-separated list of nodes, Slurm notation is also accepted")
parser.add_argument("--clusters", type=str, help="Comma-separated list of clusters. Includes all nodes in the cluster. Cannot be combined with --nodes")
parser.add_argument("--recom", action="store_true", help="Run all recommendations flag")
parser.add_argument("--reboot", action="store_true", help="Reboot flag")
parser.add_argument("--tag", action="store_true", help="Tagged nodes unhealthy")
parser.add_argument("--terminate", action="store_true", help="Terminate nodes")
parser.add_argument("--bvr", action="store_true", help="BVR flag with image OCID")
parser.add_argument("--image", type=str, help="BVR image OCID")
parser.add_argument("--details", action="store_true", help="Give details on the nodes")
args = parser.parse_args()

if args.nodes:
    nodes_list = NodeSet(args.nodes)
    logger.info(f"Processing nodes: {nodes_list}")
else: 
    nodes_list= NodeSet()
    logger.info(f"Processing all nodes")
if args.clusters:
    clusters_list = args.clusters.split(',')
    logger.info(f"Processing Clusters: {clusters_list}")
else: 
    clusters_list = []

if args.recom:
    logger.info("Recompute flag is set.")
if args.reboot:
    logger.info("Reboot flag is set.")
    if not nodes_list:
        logger.error("You need to provide a hostlist to use the reboot flag")
        exit(1)
if args.image:
    if args.bvr:
        if not nodes_list:
            logger.error("You need to provide a hostlist to use the BVR flag")
            exit(1)
        logger.info(f"BVR flag is set with image OCID: {args.image}")
    else:
        logger.error("You need to provide the BVR flag along with the image")
        exit(1)
elif args.bvr:
    if not nodes_list:
        logger.error("You need to provide a hostlist to use the BVR flag")
        exit(1)
if args.tag:
    logger.info(f"Tag flag is set")
    if not nodes_list:
        logger.error("You need to provide a hostlist to use the tag flag")
        exit(1)
if args.terminate:
    logger.info(f"Terminate flag is set with image OCID: {args.bvr}")
    if not nodes_list:
        logger.error("You need to provide a hostlist to use the terminate flag")
        exit(1)

version = sys.version_info
if version >= (3, 12):
    UTC = timezone.utc

# DB Connection Details
db_host = "localhost"
db_user = "clusterUser"
db_pw = "Cluster1234!"
db_name = "clusterDB"

unreachable_timeout = timedelta(minutes=30)

def get_ocid_from_ip(ip_address, compartment_ocid ):
    for instance in oci.pagination.list_call_get_all_results(computeClient.list_instances(compartment_id=compartment_ocid)).data:
        for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance.id).data:
            if potential_vnic_attachment.display_name is None:
                try:
                    vnic_attachment = potential_vnic_attachment
                    vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                    if vnic.private_ip == ip_address:
                        return instance.id
                except:
                    continue
    return None

def get_ipa_ocid(instance, compartment_ocid):
    if instance["cluster_name"]:
        instance_pools = oci.pagination.list_call_get_all_results(computeManagementClient.list_cluster_networks,compartment_ocid,display_name=instance["cluster_name"]).data
        if len(instance_pools):
            for instance_pool in instance_pools:
                 instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_instance_pool_instances,compartment_ocid,instance_pool.id).data
                 for instance_summary in instance_summaries:
                    if instance["ocid"]:
                        if instance_summary.id == instance["ocid"]:
                            return instance_pool.id,"CN"
                    else:
                        if instance_summary.lifecycle_state == "TERMINATED":
                            continue
                        try:
                            for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance_summary.id).data:
                                if potential_vnic_attachment.display_name is None:
                                    vnic_attachment = potential_vnic_attachment
                            vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                            if vnic.private_ip == instance["ip_address"]:
                                return instance_pool.id,"CN"
                        except:
                            continue
        instance_pools = oci.pagination.list_call_get_all_results(computeManagementClient.list_instance_pools,compartment_ocid,display_name=instance["cluster_name"]).data
        if len(instance_pools):
            for instance_pool in instance_pools:
                 instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_instance_pool_instances,compartment_ocid,instance_pool.id).data
                 for instance_summary in instance_summaries:
                    if instance["ocid"]:
                        if instance_summary.id == instance["ocid"]:
                            return instance_pool.id,"IPA"
                    else:
                        if instance_summary.lifecycle_state == "TERMINATED":
                            continue
                        try:
                            for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance_summary.id).data:
                                if potential_vnic_attachment.display_name is None:
                                    vnic_attachment = potential_vnic_attachment
                            vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                            if vnic.private_ip == instance["ip_address"]:
                                return instance_pool.id,"IPA"
                        except:
                            continue
            
        instance_pools = computeClient.list_compute_clusters(compartment_ocid,display_name=instance["cluster_name"]).data.items
        if len(instance_pools):
            for instance_pool in instance_pools:
                instance_summaries = computeClient.list_instances(compartment_ocid,compute_cluster_id=instance_pools.id).data
                for instance_summary in instance_summaries:
                    if instance["ocid"]:
                        if instance_summary.id == instance["ocid"]:
                            return instance_pool.id,"CC"
                    else:
                        if instance_summary.lifecycle_state == "TERMINATED":
                            continue
                        try:
                            for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance_summary.id).data:
                                if potential_vnic_attachment.display_name is None:
                                    vnic_attachment = potential_vnic_attachment
                            vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                            if vnic.private_ip == instance["ip_address"]:
                                return instance_pool.id,"CC"
                        except:
                            continue
    return None,"StandAlone"

def query_db(controller_hostname):
    try:
        connection = pymysql.connect(host=db_host, user=db_user, password=db_pw, database=db_name)
        logger.info("Database connection established successfully.")
    except pymysql.MySQLError as e:
        logger.error(f"Error connecting to the database: {e}")
        sys.exit(1)

    query = """
    SELECT *
    FROM nodes
    WHERE controller_name = %s;
    """
    params = (controller_hostname,)
    results = None
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(query, params)
            results = cursor.fetchall()
            logger.info("Query executed successfully. Retrieved %d records.", len(results))
    except pymysql.MySQLError as e:
        logger.error(f"Database query failed: {e}")
    finally:
        connection.close()
        logger.info("Database connection closed.")
    return results

def generateTag(tenancy):
    try:
        tag_id_list=[i.id for i in IdentityClient.list_tag_namespaces(tenancy,include_subcompartments=True,lifecycle_state="ACTIVE").data if i.name == "ComputeInstanceHostActions2"]
        logger.info(str(tag_id_list))
        if tag_id_list:
            tag_id=tag_id_list[0]
        else:
            TagNSDetails=oci.identity.models.CreateTagNamespaceDetails(compartment_id=tenancy,description="Tag for unhealthy nodes",name="ComputeInstanceHostActions2")
            tagNameSpace=IdentityClientCompositeOperations.create_tag_namespace_and_wait_for_state(TagNSDetails,wait_for_states=["ACTIVE"])
            tag_id=tagNameSpace.id
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error: {e}")


results = query_db(controller_hostname)
# Initialize node lists
configured_nodes = []
waiting_for_compute = []
terminating = []
starting = []
failing_starting = []
unreachable_nodes = []

current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
timeTH = current_time - unreachable_timeout

controller = [i for i in results if i["role"] == "controller"]
compartment_ocid=controller[0]["compartment"]

all_compute = [i for i in results if i["role"] == "compute"]
if nodes_list:
    compute=[]
    for node in nodes_list:
        if node in [i["hostname"] for i in results] or node in [i["ip_address"] for i in results] or node in [i["oci_name"] for i in results]:
            compute+=[i for i in results if (i["hostname"] == node or i["ip_address"] == node or i["oci_name"] == node)]
        else:
            logger.error(f"Node: {node} is not present in the DB") 
elif clusters_list:
    compute=[]
    for cluster in clusters_list:
        compute+=[i for i in results if i["cluster_name"] == cluster]
    if not compute:
        logger.error(f"Cluster: {cluster} has no matching nodes present in the DB")
    nodes_list=NodeSet(','.join([i["hostname"] for i in compute]))
else:
    compute=[i for i in results if i["role"] == "compute" or i["controller_status"] == "waiting_for_info"]

for i in compute:
    if i["controller_status"] == "configured" and i["compute_status"] == "configured":
        configured_nodes.append(i)
    elif i["controller_status"] == "configured" and i["compute_status"] == "configuring":
        waiting_for_compute.append(i)
    elif i["controller_status"] == "terminating":
        terminating.append(i)
    elif i["controller_status"] == "waiting_for_info":
        startedTime = datetime.strptime(i["startedTime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if startedTime < timeTH:
            failing_starting.append(i)
        starting.append(i)
    if i["controller_status"] == "configured" and i["compute_status"] in ["configured", "configuring"]:
        lastTimeReachable = datetime.strptime(i["lastTimeReachable"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if lastTimeReachable < timeTH:
            unreachable_nodes.append(i)

logger.info(f"Counts: Configured: {len(configured_nodes)}, Configuring: {len(waiting_for_compute)}, "
            f"Starting: {len(starting)}, Terminating: {len(terminating)}")

logger.info(f"Configured Nodes: {NodeSet(','.join([i['hostname'] for i in configured_nodes]))}")
logger.info(f"Configuring Nodes: {NodeSet(','.join([i['hostname'] for i in waiting_for_compute]))}")
logger.info(f"Terminating Nodes: {NodeSet(','.join([i['hostname'] for i in terminating]))}")
logger.info(f"Starting Nodes: {','.join([i['ip_address'] for i in starting])}")

if failing_starting:
    logger.warning(f"Some nodes are failing to start: {','.join([i['ip_address'] for i in failing_starting])}")
if unreachable_nodes:
    logger.warning(f"Some nodes haven't responded in a while: {','.join([i['ip_address'] for i in unreachable_nodes])}")

if args.details:
    for i in compute:
        logger.info(i)

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

if failing_starting or unreachable_nodes:
    if args.recom:
        for instance in unreachable_nodes:
            computeClient.instance_action(instance_id=instance["ocid"],action="RESET")
            logger.info("Rebooting: "+instance["hostname"]+" with oci name "+instance["oci_name"]+" with IP "+instance["ip_address"]+" and OCID:"+instance["ocid"])

        for instance in failing_starting:
            instance_ocid=get_ocid_from_ip(i["ip_address"], compartment_ocid )
            computeClient.instance_action(instance_id=i["ocid"],action="RESET")
            logger.info("Rebooting: "+instance["ip_address"]+" and OCID:"+instance_ocid)
    else:
        logger.warning("If you would like to reboot the unreachables nodes, rerun this script with --recomm")

if args.reboot:
    for i in nodes_list:
        for instance in compute:
            if i == instance["hostname"] or i == instance["oci_name"] or i == instance["ip_address"]:
                if len(instance["ocid"]):
                    computeClient.instance_action(instance_id=instance["ocid"],action="RESET")
                    logger.info("Rebooting: "+instance["hostname"]+" with oci name "+instance["oci_name"]+" with IP "+instance["ip_address"]+" and OCID:"+instance["ocid"])
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=get_ocid_from_ip(i["ip_address"], compartment_ocid )
                    logger.info("Rebooting: "+instance["ip_address"]+" and OCID:"+instance_ocid)
                    if instance["hostname"]:
                        logger.info("Hostname: "+instance["hostname"]+" with oci name "+instance["oci_name"])

if args.bvr:
    for i in nodes_list:
        for instance in compute:
            if i == instance["hostname"] or i == instance["oci_name"] or i == instance["ip_address"]:
                if len(instance["ocid"]):
                    instance_ocid=instance["ocid"]
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=get_ocid_from_ip(i["ip_address"], compartment_ocid )

                update_instance_source_details = oci.core.models.UpdateInstanceSourceViaImageDetails()
                update_instance_source_details.image_id = args.image
                update_instance_source_details.is_preserve_boot_volume_enabled = True
                update_instance_source_details.is_force_stop_enabled = True
                update_instance_details = oci.core.models.UpdateInstanceDetails()
                update_instance_details.source_details = update_instance_source_details
                update_instance_response = ComputeClientCompositeOperations.update_image_and_wait_for_state(instance_ocid, update_instance_details,wait_for_states=["RUNNING"])

if args.tag:
    for i in nodes_list:
        for instance in compute:
            if i == instance["hostname"] or i == instance["oci_name"] or i == instance["ip_address"]:
                if len(instance["ocid"]):
                    instance_ocid=instance["ocid"]
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=get_ocid_from_ip(i["ip_address"], compartment_ocid )
                instance = computeClient.get_instance(instance_id=instance_ocid).data
                tags = instance.defined_tags
                tags.update({'ComputeInstanceHostActions': { 'CustomerReportedHostStatus': 'unhealthy' }})
                update_instance_details = oci.core.models.UpdateInstanceDetails(defined_tags=tags)
                logger.info("Updating tags on instance: "+i+" with OCID:"+instance_ocid)
                try:
                    update_instance_response = ComputeClientCompositeOperations.update_instance_and_wait_for_state(instance_ocid, update_instance_details,wait_for_states=["RUNNING"])
                except oci.exceptions.ServiceError as e:
                    logger.error("The tag does not exists or the controller doesn't have acces to the tag")
                    logger.error("Make sure the Tag namespace ComputeInstanceHostActions exists with the defined tag: CustomerReportedHostStatus")



if args.terminate:
    for i in nodes_list:
        for instance in compute:
            if i == instance["hostname"] or i == instance["oci_name"] or i == instance["ip_address"]:
                if len(instance["ocid"]):
                    instance_ocid=instance["ocid"]
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=get_ocid_from_ip(i["ip_address"], compartment_ocid )
                
                try:
                    ipa_ocid,ipa_type=get_ipa_ocid(instance, compartment_ocid)
                    if ipa_type == "StandAlone" or ipa_type == "CC":
                        logger.info("Terminating node:"+i+"with details"+instance["hostname"]+","+instance["oci_name"]+","+instance["ip_address"])
                        ComputeClientCompositeOperations.terminate_instance_and_wait_for_state(instance_ocid,wait_for_states=["TERMINATING","TERMINATED"])
                    elif ipa_type == "IPA" or ipa_type == "CN":
                        logger.info("Terminating node:"+i+"with details"+instance["hostname"]+","+instance["oci_name"]+","+instance["ip_address"])
                        instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=instance_ocid,is_auto_terminate=True,is_decrement_size=True)
                        ComputeManagementClientCompositeOperations.detach_instance_pool_instance_and_wait_for_work_request(ipa_ocid,instance_details)
                except oci.exceptions.ServiceError as e:
                    logger.error(f"Error: {e}")