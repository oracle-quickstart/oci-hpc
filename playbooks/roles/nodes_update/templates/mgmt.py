import pymysql
from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
import sys
import logging
import argparse
from datetime import datetime, timedelta, timezone
import time
import random
import string

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
parser.add_argument("--add", type=int, default=0, help="Add nodes to the cluster defined")
args = parser.parse_args()

if args.nodes:
    nodes_list = NodeSet(args.nodes)
    logger.info(f"Processing nodes: {nodes_list}")
else: 
    nodes_list= NodeSet()
    logger.info(f"Processing all nodes")
if args.clusters:
    clusters_list_defined = args.clusters.split(',')
    logger.info(f"Processing Clusters: {clusters_list_defined}")
else: 
    clusters_list_defined = []

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
    logger.info(f"Terminate flag is set")
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
    
def get_summary(compartment_ocid,clustername):
    
    running_clusters = 0
    running_clusters_info=[]
    scaling_clusters = 0
    scaling_clusters_info=[]
    cn_summary=None

    #Looking for CNs
    CN = "CN"
    cn_summaries = computeManagementClient.list_cluster_networks(compartment_ocid,display_name=clustername).data
    if len(cn_summaries) > 0:
        for cn_summary_tmp in cn_summaries:
            if cn_summary_tmp.lifecycle_state == "RUNNING":
                cn_summary = cn_summary_tmp
                running_clusters = running_clusters + 1
                running_clusters_info.append([cn_summary_tmp,"CN"])
            elif cn_summary_tmp.lifecycle_state == "SCALING":
                scaling_clusters = scaling_clusters + 1
                scaling_clusters_info.append([cn_summary_tmp,"CN"])

    # Looking for CCs        
    try:
        cn_summaries = computeClient.list_compute_clusters(compartment_ocid,display_name=clustername).data.items
    except:
        logger.error("The list_compute_clusters call returned an error, considering no Compute Clusters are present")
        cn_summaries = []
    if len(cn_summaries) > 0:
        CN = "CC"
        for cn_summary_tmp in cn_summaries:
            if cn_summary_tmp.lifecycle_state == "ACTIVE" and cn_summary_tmp.display_name == clustername :
                cn_summary = cn_summary_tmp
                running_clusters = running_clusters + 1
                running_clusters_info.append([cn_summary_tmp,"CC"])

    # Looking for IPAs   
    cn_summaries = computeManagementClient.list_instance_pools(compartment_ocid,display_name=clustername).data
    if len(cn_summaries) > 0:
        CN = "IPA"
        for cn_summary_tmp in cn_summaries:
            if cn_summary_tmp.id in [i[0].id for i in running_clusters_info if i[1] == "CN"]:
                # Ignore matching IPAs for existing CNs
                continue
            else:
                if cn_summary_tmp.lifecycle_state == "RUNNING":
                    cn_summary = cn_summary_tmp
                    running_clusters = running_clusters + 1
                    running_clusters_info.append([cn_summary_tmp,"IPA"])
                elif cn_summary_tmp.lifecycle_state == "SCALING":
                    scaling_clusters = scaling_clusters + 1
                    scaling_clusters_info.append([cn_summary_tmp,"IPA"])

    if running_clusters == 0:
        if scaling_clusters:
            logger.error(f"No running cluster was found but there is(are) {len(scaling_clusters)} cluster(s) in SCALING mode, try rerunning in a moment")
        else:
            logger.error("The cluster was not found")
        return None,None,True
    
    if running_clusters > 1:
        logger.info("There were multiple running clusters with this name")
        for i, cluster in enumerate(running_clusters_info):
            print(f"{i+1}. {cluster[0].id} of type {cluster[1]}")
        # Ask user to choose which cluster to scale
        choice = int(input("Enter the number of the cluster use: ")) - 1
        cn_summary = running_clusters_info[choice][0]

    if CN == "CN":
        ip_summary=cn_summary.instance_pools[0]
    elif CN == "CC":
        ip_summary=None
    else:
        ip_summary=cn_summary
    return cn_summary,ip_summary,CN

def get_instances(compartment_ocid,cn_ocid,CN):
    cn_instances=[]
    if CN == "CC":
        instances = computeClient.list_instances(compartment_ocid,compute_cluster_id=cn_ocid,sort_by="TIMECREATED").data
        for instance in instances:
            if instance.lifecycle_state == "TERMINATED":
                continue
            try:
                for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance.id).data:
                    if potential_vnic_attachment.display_name is None:
                        vnic_attachment = potential_vnic_attachment
                vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
            except:
                continue
            cn_instances.append({'display_name':instance.display_name,'ip':vnic.private_ip,'ocid':instance.id})
    else:
        if CN == "CN":
            instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_cluster_network_instances,compartment_ocid,cn_ocid,sort_by="TIMECREATED").data
        else:
            instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_instance_pool_instances,compartment_ocid,cn_ocid,sort_by="TIMECREATED").data
        for instance_summary in instance_summaries:
            try:
                instance=computeClient.get_instance(instance_summary.id).data
                for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance.id).data:
                    if potential_vnic_attachment.display_name is None:
                        vnic_attachment = potential_vnic_attachment
                vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
            except:
                continue
            cn_instances.append({'display_name':instance_summary.display_name,'ip':vnic.private_ip,'ocid':instance_summary.id,'created':instance_summary})
    return cn_instances

def getLaunchInstanceDetails(instance,compartment_ocid,cn_ocid,clustername):

    agent_config=instance.agent_config
    agent_config.__class__ = oci.core.models.LaunchInstanceAgentConfigDetails

    for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance.id).data:
        if potential_vnic_attachment.display_name is None:
            vnic_attachment = potential_vnic_attachment
    create_vnic_details=oci.core.models.CreateVnicDetails(assign_public_ip=False,subnet_id=vnic_attachment.subnet_id)

    shape_config=instance.shape_config
    try:
        nvmes=shape_config.local_disks
        launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,nvmes=nvmes,ocpus=shape_config.ocpus)
    except:
        launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,ocpus=shape_config.ocpus)

    new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+clustername
    launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=instance.availability_domain, compartment_id=compartment_ocid,compute_cluster_id=cn_ocid,shape=instance.shape,shape_config=launchInstanceShapeConfigDetails,source_details=instance.source_details,metadata=instance.metadata,display_name=new_display_name,freeform_tags=instance.freeform_tags,create_vnic_details=create_vnic_details)
    return launch_instance_details

def add_node_to_cluster(clustername,number_of_nodes,compartment_ocid):
    cn_summary,ip_summary,CN = get_summary(compartment_ocid,clustername)

    logger.info(cn_summary.id+" "+ip_summary.id+" "+CN)
    if cn_summary is None:
        exit(1)
    else:
        cn_instances = get_instances(compartment_ocid,cn_summary.id,CN)
        if CN == "CC":
            current_size=len(cn_instances)
            if len(cn_instances) == 0:
                 logger.error("The resize script cannot work for a compute cluster if the size is there is no node in the cluster")
            else:
                instance=computeClient.get_instance(cn_instances[0]['ocid']).data
                logger.info(f"Launching {number_of_nodes} in the Compute Cluster")
                for i in range(number_of_nodes):
                    launch_instance_details=getLaunchInstanceDetails(instance,compartment_ocid,cn_summary.id,clustername)
                    ComputeClientCompositeOperations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
        else:
            logger.info("else")
            size = ip_summary.size + number_of_nodes
            update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
            logger.info(f"Launching {number_of_nodes} in the Compute Cluster for a total size of {size}")
            ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(ip_summary.id,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
            logger.info(f"done")
        cn_summary,ip_summary,CN = get_summary(compartment_ocid,clustername)
        if CN == "CC":
            new_cn_instances = get_instances(compartment_ocid,cn_summary.id,CN)
            newsize=len(new_cn_instances)
        else:
            new_cn_instances = get_instances(compartment_ocid,cn_summary.id,CN)
            newsize=ip_summary.compartment_ocid
        if newsize == current_size:
            logger.error("No node was added, please check the work requests of the Cluster Network and Instance Pool to see why")
            exit(1)

#def generateTag(tenancy):
#    try:
#        tag_id_list=[i.id for i in IdentityClient.list_tag_namespaces(tenancy,include_subcompartments=True,lifecycle_state="ACTIVE").data if i.name == "ComputeInstanceHostActions2"]
#        logger.info(str(tag_id_list))
#        if tag_id_list:
#            tag_id=tag_id_list[0]
#        else:
#            TagNSDetails=oci.identity.models.CreateTagNamespaceDetails(compartment_id=tenancy,description="Tag for unhealthy nodes",name="ComputeInstanceHostActions2")
#            tagNameSpace=IdentityClientCompositeOperations.create_tag_namespace_and_wait_for_state(TagNSDetails,wait_for_states=["ACTIVE"])
#            tag_id=tagNameSpace.id
#    except oci.exceptions.ServiceError as e:
#        logger.error(f"Error: {e}")


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
elif clusters_list_defined:
    compute=[]
    for cluster in clusters_list_defined:
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
        
clusters_list_found=list(set([i["cluster_name"] for i in compute ]))

logger.info(f"Counts: Configured: {len(configured_nodes)}, Configuring: {len(waiting_for_compute)}, "
            f"Starting: {len(starting)}, Terminating: {len(terminating)}")

logger.info(f"Configured Nodes: {NodeSet(','.join([i['hostname'] for i in configured_nodes]))}")
logger.info(f"Configuring Nodes: {NodeSet(','.join([i['hostname'] for i in waiting_for_compute]))}")
logger.info(f"Terminating Nodes: {NodeSet(','.join([i['hostname'] for i in terminating]))}")
logger.info(f"Starting Nodes: {','.join([i['ip_address'] for i in starting])}")

logger.info("Clusters: +"+','.join(clusters_list_found))

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

        if failing_starting:
            logger.info(f"Restarting the configuration script on: {NodeSet(','.join([i['ip_address'] for i in failing_starting]))}")
            task = task_self()
            task.shell("/config/compute.sh", nodes=NodeSet(','.join([i['ip_address'] for i in failing_starting])))
            task.run()
            logger.info(f"Reconfiguration is done, logs are available at /config/logs/")
    else:
        if failing_starting:
            logger.warning("If you would like to reconfigure the starting nodes, rerun this script with --recomm")
        if unreachable_nodes:
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
    if args.image:
        image_ocid=args.image
    else:
        custom_images=list_custom_images(compartment_ocid)
        for i, img in enumerate(custom_images):
            print(f"{i+1}. {img.display_name} ({img.id})")
        # Ask user to choose a custom image
        choice = int(input("Enter the number of the custom image to use: ")) - 1
        image_ocid = custom_images[choice].id
        logger.info(image_ocid)
    for i in nodes_list:
        for instance in compute:
            if i == instance["hostname"] or i == instance["oci_name"] or i == instance["ip_address"]:
                if len(instance["ocid"]):
                    instance_ocid=instance["ocid"]
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=get_ocid_from_ip(i["ip_address"], compartment_ocid )

                update_instance_source_details = oci.core.models.UpdateInstanceSourceViaImageDetails()
                update_instance_source_details.image_id = image_ocid
                update_instance_source_details.is_preserve_boot_volume_enabled = True
                update_instance_source_details.is_force_stop_enabled = True
                update_instance_details = oci.core.models.UpdateInstanceDetails()
                update_instance_details.source_details = update_instance_source_details
                logger.info(f"Replacing BV for instance: {instance["hostname"]}")
                ComputeClientCompositeOperations.update_instance_and_wait_for_state(instance_ocid, update_instance_details,wait_for_states=["RUNNING"])

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

if args.add:
    cluster_to_add = None
    if len(clusters_list_defined)==0:
        logger.info(f"No Cluster was defined to add")
        if len(clusters_list_found) == 1:
            cluster_to_add=clusters_list_found[0]
            logger.info(f"Using the 1 clustername found: {clusters_list_found[0]}")
        else:
            logger.error(f"There were {len(clusters_list_found)} clusters found and none specified, not adding nodes")
    elif len(clusters_list_defined)>1:
        logger.error(f"Only Specify one cluster for resize")
    elif len(clusters_list_defined)==1:
        cluster_to_add=clusters_list_defined[0]
    if not cluster_to_add is None:
        logger.info(f"Adding a node to: {cluster_to_add}")
        add_node_to_cluster(cluster_to_add,args.add,compartment_ocid)

