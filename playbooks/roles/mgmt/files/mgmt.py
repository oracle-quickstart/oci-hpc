from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
import sys
from mgmt_shared_logging import logger
import argparse
from datetime import datetime, timedelta, timezone
import mgmt_utils 
import json
import time

# Argument parsing
parser = argparse.ArgumentParser(description="Process node list and flags.")
parser.add_argument("-n","--nodes", type=str, help="Comma-separated list of nodes, Slurm notation is also accepted")
parser.add_argument("-c","--clusters", type=str, help="Comma-separated list of clusters. Includes all nodes in the cluster. Cannot be combined with --nodes")
parser.add_argument("-a","--all", action="store_true", help="Specify all compute nodes")
parser.add_argument("-recom","--recom", action="store_true", help="Run all recommendations flag")
parser.add_argument("-r","--reboot", action="store_true", help="Reboot flag")
parser.add_argument("-tag","--tag", action="store_true", help="Tagged nodes unhealthy")
parser.add_argument("-t","--terminate", action="store_true", help="Terminate nodes")
parser.add_argument("-bvr","--bvr", action="store_true", help="Replace the Boot Volume")
parser.add_argument("-conf","--configure", action="store_true", help="Rerun the cloud-init script")
parser.add_argument("-i","--image", type=str, help=argparse.SUPPRESS)
parser.add_argument("-d","--details", action="store_true", help="Give details on the nodes")
parser.add_argument("-add","--add", type=int, default=0, help="Add nodes to the cluster defined")
parser.add_argument("-cc","--create_cluster", type=str, default="", help="Specify the name of the cluster you want to create, more options with --context_help")
parser.add_argument("-dc","--delete_cluster", type=str, default="", help="Specify the name of the cluster you want to delete")
parser.add_argument("-cc_itype","--create_cluster_instance_type", type=str, help=argparse.SUPPRESS)
parser.add_argument("-cc_config","--create_cluster_inst_config", type=str, help=argparse.SUPPRESS)
parser.add_argument("-cc_type","--create_cluster_type", type=str, choices=['CN', 'CC', 'IPA', 'SA'], help=argparse.SUPPRESS)
parser.add_argument("-cc_c","--create_cluster_count", type=int, help=argparse.SUPPRESS)
parser.add_argument("-cc_ad","--create_cluster_ad", type=str, help=argparse.SUPPRESS)
parser.add_argument("-cc_sub","--create_cluster_subnet", type=str, help=argparse.SUPPRESS)
parser.add_argument("-ch","--context_help", action="store_true", help="Gives more help about specific flags")
args = parser.parse_args()

if args.context_help:
    if args.create_cluster:
        print("--create_cluster_instance_type INSTANCE_TYPE             Specify an instance type from /opt/oci-hpc/conf/queues.conf")
        print("--create_cluster_inst_config INSTANCE_CONFIG             Specify an instance configuration OCID")
        print("--create_cluster_count COUNT                             Specify the initial number of nodes")
        print("--create_cluster_type CLUSTER_TYPE                       With instance configuration: Specify a type of cluster: CN=Cluster Network, CC=Compute Cluster, IPA=Instance Pool, SA=Stand Alone Instances")
        print("--create_cluster_ad AD                                   With instance configuration: Specify the AD of the cluster if using INSTANCE_CONFIG OCID")
        print("--create_cluster_subnet SUBNET                           With instance configuration: Specify the subnet OCID if using INSTANCE_CONFIG OCID")
        exit(1)
    if args.bvr:
        print("--image IMAGE            Specify an image OCID to run Boot Volume Replacement")
    if args.add:
        print("--clusters clustername            Specify a unique clustername")
    exit(1)
#Check if arguments make sense
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
if nodes_list and clusters_list_defined:
    logger.error("You cannot provide a hostlist and a clusterlist")
    exit(1)
if args.recom:
    logger.info("Recompute flag is set.")
if args.reboot:
    logger.info("Reboot flag is set.")
    if not nodes_list and not clusters_list_defined and not args.all :
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the reboot flag")
        exit(1)
if args.image:
    if args.bvr:
        if not nodes_list and not clusters_list_defined and not args.all:
            logger.error("You need to provide a hostlist, a clusterlist or --all to use the bvr flag")
            exit(1)
        logger.info(f"BVR flag is set with image OCID: {args.image}")
    else:
        logger.error("You need to provide the BVR flag along with the image")
        exit(1)
elif args.bvr:
    if not nodes_list and not clusters_list_defined and not args.all:
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the bvr flag")
        exit(1)
if args.tag:
    logger.info(f"Tag flag is set")
    if not nodes_list:
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the tag flag")
        exit(1)
if args.terminate:
    logger.info(f"Terminate flag is set")
    if not nodes_list and not clusters_list_defined and not args.all:
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the terminate flag")
        exit(1)
if args.all:
    if nodes_list or clusters_list_defined:
        logger.error("You cannot provide a hostlist or a clusterlist with the --all flag")
        exit(1)

if args.add:
    if args.create_cluster or args.delete_cluster: 
        logger.error("You cannot add and create/delete a cluster in the same command")
        exit(1)

if args.create_cluster:
    if args.delete_cluster:
        logger.error("You cannot create and delete a cluster in the same command")
        exit(1)
    if args.create_cluster_instance_type:
        if args.create_cluster_inst_config:
            logger.error("You cannot specify both instance_type and instance_config")
            exit(1)
        elif args.create_cluster_type or args.create_cluster_ad or args.create_cluster_subnet:
            logger.warning("When specifying instance_type to create a cluster; AD, Subnet and Cluster Type are ignored")
        
version = sys.version_info
if version >= (3, 12):
    UTC = timezone.utc

unreachable_timeout = timedelta(minutes=30)

results = mgmt_utils.query_db()
# Initialize node lists
configured_nodes = []
waiting_for_compute = []
terminating = []
starting = []
failing_starting = []
unreachable_nodes = []
hc_reboot = []
hc_terminate = []

current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
timeTH = (current_time - unreachable_timeout).replace(tzinfo=timezone.utc)

controller = [i for i in results if i["role"] == "controller"]
if len(controller) > 1:
    logger.error(f"There are multiple controller in the DB, Using {controller[0]['hostname']}")
 
controller_hostname=controller[0]['hostname']
compartment_ocid=controller[0]["compartment"]

login = [i for i in results if i["role"] == "login"]

clusters = [i["cluster_name"] for i in results if i["role"] == "compute"]
if args.create_cluster:
    if args.create_cluster in clusters:
        logger.error("You are trying to create a cluster with a name that already exists, this will add confusion. Please rename")
        exit(1)

if nodes_list:
    compute=[]
    compute_with_terminated = [] # Cannot show terminated nodes with nodes list of cluster defined, only -a
    for node in nodes_list:
        if node in [i["hostname"] for i in results] or node in [i["ip_address"] for i in results] or node in [i["oci_name"] for i in results]:
            compute+=[i for i in results if (i["hostname"] == node or i["ip_address"] == node or i["oci_name"] == node)]
        else:
            logger.error(f"Node: {node} is not present in the DB")
elif clusters_list_defined:
    compute=[]
    for cluster in clusters_list_defined:
        compute+=[i for i in results if i["cluster_name"] == cluster and i["role"] == "compute"]
    if not compute:
        logger.error(f"Cluster: {cluster} has no matching nodes present in the DB")
    nodes_list=NodeSet(','.join([i["hostname"] for i in compute]))
else:
    compute_with_terminated=[i for i in results if i["role"] == "compute" or i["controller_status"] == "waiting_for_info"]
    compute=[i for i in results if ( i["role"] == "compute" or i["controller_status"] == "waiting_for_info" ) and (i["status"] != "terminated")]

for i in compute:
    if i["controller_status"] == "configured" and i["compute_status"] == "configured":
        configured_nodes.append(i)
    elif i["compute_status"] == "configuring":
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
    if i["healthcheck_recomandation"] == "Reboot":
        hc_reboot.append(i)
    elif i["healthcheck_recomandation"] == "Terminate":
        hc_terminate.append(i)

clusters_list_found=[i for i in list(set([i["cluster_name"] for i in compute ])) if not i is None]
logger.info(f"Counts: Configured: {len(configured_nodes)}, Configuring: {len(waiting_for_compute)}, "
            f"Starting: {len(starting)}, Terminating: {len(terminating)}")

logger.info(f"Configured Nodes: {NodeSet(','.join([i['hostname'] for i in configured_nodes]))}")
logger.info(f"Configuring Nodes: {NodeSet(','.join([i['hostname'] for i in waiting_for_compute]))}")
logger.info(f"Terminating Nodes: {NodeSet(','.join([i['hostname'] for i in terminating]))}")
logger.info(f"Starting Nodes: {','.join([i['ip_address'] for i in starting])}")
logger.info(f"Healthcheck Recommendations to Reboot: {NodeSet(','.join([i['hostname'] for i in hc_reboot]))}")
logger.info(f"Healthcheck Recommendations to Terminate: {NodeSet(','.join([i['hostname'] for i in hc_terminate]))}")

logger.info("Clusters: "+','.join(clusters_list_found))
logger.info(f"Login Nodes: {NodeSet(','.join([i['hostname'] for i in login]))}")

if failing_starting:
    logger.warning(f"Some nodes are failing to start: {','.join([i['ip_address'] for i in failing_starting])}")
if unreachable_nodes:
    logger.warning(f"Some nodes haven't responded in a while: {','.join([i['ip_address'] for i in unreachable_nodes])}")

if args.details:
    if args.all:
        for i in compute_with_terminated:
            print(json.dumps(i, indent=4).replace("\\n", "\n"))
    else:
        for i in compute:
            print(json.dumps(i, indent=4).replace("\\n", "\n"))


if failing_starting or unreachable_nodes or hc_reboot or hc_terminate:
    if args.recom:
        ocids=[]
        for instance in unreachable_nodes + hc_reboot:
            if len(instance["ocid"]):
                instance_ocid=instance["ocid"]
            else:
                logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                instance_ocid=mgmt_utils.get_ocid_from_ip(node["ip_address"], compartment_ocid )
            if not instance_ocid in ocids:
                ocids.append(instance_ocid)
                mgmt_utils.force_reboot(instance_ocid)
                logger.info("Rebooting: "+instance["hostname"]+" with oci name "+instance["oci_name"]+" with IP "+instance["ip_address"]+" and OCID:"+instance["ocid"])
        if failing_starting:
            logger.info(f"Restarting the configuration script on: {NodeSet(','.join([i['ip_address'] for i in failing_starting]))}")
            task = task_self()
            task.shell("/config/compute.sh", nodes=NodeSet(','.join([i['ip_address'] for i in failing_starting])))
            task.run()
            logger.info(f"Reconfiguration is done, logs are available at /config/logs/")
        for instance in hc_terminate:
            if len(instance["ocid"]):
                instance_ocid=instance["ocid"]
                node=instance["hostname"]
            else:
                logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                instance_ocid=mgmt_utils.get_ocid_from_ip(node["ip_address"], compartment_ocid )
                node=instance["ip_address"]
            mgmt_utils.tag_unhealthy(node,instance_ocid)
            mgmt_utils.terminate_instance(node,instance,instance_ocid,compartment_ocid)
            logger.info("Tagging and Terminating because of healthcheck: "+instance["hostname"]+" with oci name "+instance["oci_name"]+" with IP "+instance["ip_address"]+" and OCID:"+instance["ocid"])
    else:
        if failing_starting:
            logger.warning("If you would like to reconfigure the starting nodes, rerun this script with --recomm")
        if unreachable_nodes:
            logger.warning("If you would like to reboot the unreachables nodes, rerun this script with --recomm")
        if hc_reboot or hc_terminate:
            logger.warning("If you would like to reboot or terminate based on healthcheck results, rerun this script with --recomm")

if args.reboot:
    for node in nodes_list:
        for instance in compute:
            if node == instance["hostname"] or node == instance["oci_name"] or node == instance["ip_address"]:
                if len(instance["ocid"]):
                    mgmt_utils.force_reboot(instance["ocid"])
                    logger.info("Rebooting: "+instance["hostname"]+" with oci name "+instance["oci_name"]+" with IP "+instance["ip_address"]+" and OCID:"+instance["ocid"])
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=mgmt_utils.get_ocid_from_ip(node["ip_address"], compartment_ocid )
                    logger.info("Rebooting: "+instance["ip_address"]+" and OCID:"+instance_ocid)
                    if instance["hostname"]:
                        logger.info("Hostname: "+instance["hostname"]+" with oci name "+instance["oci_name"])

if args.bvr:
    if args.image:
        image_ocid=args.image
    else:
        custom_images=mgmt_utils.list_custom_images(compartment_ocid)
        for i, img in enumerate(custom_images):
            print(f"{i+1}. {img.display_name} ({img.id})")
        # Ask user to choose a custom image
        choice = int(input("Enter the number of the custom image to use: ")) - 1
        image_ocid = custom_images[choice].id
        image_name = custom_images[choice].display_name
        logger.info(f"This image was chosen {image_name} with OCID {image_ocid}")
    count = 0
    parallelism = 10
    for node in nodes_list:
        for instance in compute:
            if node == instance["hostname"] or node == instance["oci_name"] or node == instance["ip_address"]:
                if len(instance["ocid"]):
                    instance_ocid=instance["ocid"]
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=mgmt_utils.get_ocid_from_ip(node["ip_address"], compartment_ocid )
                logger.info(f"Replacing BV for instance: "+instance["hostname"])
                mgmt_utils.instance_bvr(instance_ocid,image_ocid)
                count +=1
                if count > parallelism:
                    logger.info(f"Taking a break after {parallelism} instances")
                    time.sleep(30)
                    count = 0

if args.tag:
    for node in nodes_list:
        for instance in compute:
            if node == instance["hostname"] or node == instance["oci_name"] or node == instance["ip_address"]:
                if len(instance["ocid"]):
                    instance_ocid=instance["ocid"]
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=mgmt_utils.get_ocid_from_ip(node["ip_address"], compartment_ocid )
                mgmt_utils.tag_unhealthy(node,instance_ocid)
if args.configure:
    config_list=[]
    for node in nodes_list:
        for instance in compute:
            if node == instance["hostname"] or node == instance["oci_name"] or node == instance["ip_address"]:
                config_list.append(instance)
    logger.info(f"Restarting the configuration script on: {NodeSet(','.join(nodes_list))}")
    task = task_self()
    task.shell("sudo /config/cloud-init.sh", nodes=NodeSet(','.join([i['ip_address'] for i in config_list])))
    task.run()
    logger.info(f"Reconfiguration is done, logs are available at /config/logs/")

if args.terminate:
    for node in nodes_list:
        for instance in compute:
            if node == instance["hostname"] or node == instance["oci_name"] or node == instance["ip_address"]:
                if len(instance["ocid"]):
                    instance_ocid=instance["ocid"]
                else:
                    logger.info("Trying to get the OCID from the ip: "+instance["ip_address"])
                    instance_ocid=mgmt_utils.get_ocid_from_ip(node["ip_address"], compartment_ocid )
                mgmt_utils.terminate_instance(node,instance,instance_ocid,compartment_ocid)

if args.add:
    cluster_to_add = None
    if len(clusters_list_defined)==0:
        logger.info(f"No Cluster was defined to add")
        if len(clusters_list_found) == 1:
            cluster_to_add=clusters_list_found[0]
            logger.info(f"Using the 1 clustername found: {clusters_list_found[0]}")
        else:
            logger.error(f"There were {len(clusters_list_found)} clusters found and none specified, specify one of the cluster")
            for i, clustername in enumerate(clusters_list_found):
                print(f"{i+1}. {clustername}")
            choice_config = int(input("Enter the number of the cluster to use: ")) - 1
            cluster_to_add=clusters_list_found[choice_config]
    elif len(clusters_list_defined)>1:
        logger.error(f"Only Specify one cluster for resize")
    elif len(clusters_list_defined)==1:
        cluster_to_add=clusters_list_defined[0]
    if not cluster_to_add is None:
        logger.info(f"Adding a node to: {cluster_to_add}")
        mgmt_utils.add_node_to_cluster(cluster_to_add,args.add,compartment_ocid)

if args.create_cluster:
    clustername = args.create_cluster
    if args.create_cluster_count:
        count = args.create_cluster_count
    else:
        # Ask user to choose a custom image
        choice = int(input("How many nodes need to be created in the cluster: "))
        count = choice
    availabilitydomains = mgmt_utils.guess_availabilitydomain(compartment_ocid)
    if len(availabilitydomains)==1:
        availabilitydomain=availabilitydomains[0]
    elif args.create_cluster_ad:
        availabilitydomain=args.create_cluster_ad
    else:
        for i, ad in enumerate(availabilitydomains):
            print(f"{i+1}. {ad} ")
            choice_ad = int(input("Enter the AD index: ")) - 1
            availabilitydomain=choice_ad
            logger.info(f"This AD was chosen {availabilitydomain}")
    instance_config_ocid=None
    instance_type=None
    if args.create_cluster_instance_type is None and args.create_cluster_inst_config is None:
        # Ask user to choose an instance configuration        
        choice = input("How would you like to specify the cluster configuration: OCID or queues : ")
        if choice.lower() == "ocid" or choice.lower() == "o" or choice.lower() == "config" or choice.lower() == "ic":
            instance_config_list = mgmt_utils.list_instance_configs(compartment_ocid)
            for i, ic in enumerate(instance_config_list):
                print(f"{i+1}. {ic.display_name} ({ic.id})")
            choice_config = int(input("Enter the number of the instance configuration to use: ")) - 1
            instance_config_ocid = instance_config_list[choice_config].id
            instance_config_name = instance_config_list[choice_config].display_name
            logger.info(f"This instance configuration was chosen {instance_config_name} with OCID {instance_config_ocid}")
        elif choice.lower() == "queues" or choice.lower() == "queues.conf" or choice.lower() == "q":
            instance_type_list = mgmt_utils.list_instance_types()
            for i, it in enumerate(instance_type_list):
                print(f"{i+1}. {it['name']} ({it['partition']})")
            choice_type = int(input("Enter the number of the instance type to use: ")) - 1
            instance_type=instance_type_list[choice_type]
            logger.info(f"This instance configuration was chosen {instance_type['name']} with partition {instance_type['partition']}")
    if args.create_cluster_instance_type or not instance_type is None:
        if instance_type is None:
            instance_type_found=mgmt_utils.get_instance_type(args.create_cluster_instance_type)
            if instance_type_found is None:
                logger.error(f"The Instance type {args.create_cluster_instance_type} does not exists in /opt/oci-hpc/conf/queues.conf")
                exit(1)
            else:
                instance_type=instance_type_found
        if instance_type["cluster_network"]:
            if instance_type["compute_cluster"]:
                cluster_type="CC"
                if args.create_cluster_subnet:
                    subnet_id=args.create_cluster_subnet
                else:
                    subnet_id=None
                try:
                    cluster = mgmt_utils.create_cluster(cluster_type,instance_type,None,count,compartment_ocid,clustername,availabilitydomain,subnet_id,controller_hostname)
                except Exception as e:
                    logger.error(f"Could not create the cluster with error {e}")
                    mgmt_utils.remove_inventory(clustername)
            else:
                cluster_type="CN"
        else:
            cluster_type="IPA"
        if cluster_type != "CC":
            instance_config=mgmt_utils.generate_instance_config(instance_type,controller_hostname,clustername)
            instance_config_ocid=instance_config.id
            subnet_id=instance_type["private_subnet_id"]
    elif args.create_cluster_inst_config or not instance_config_ocid is None:
        if args.create_cluster_inst_config:
            instance_config_ocid = args.create_cluster_inst_config
        if args.create_cluster_type:
            cluster_type=args.create_cluster_type
        else:
            while True:
                # Ask user to choose a custom image
                choice_cluster_type = input("What type of cluster would you like: CN=Cluster Network, CC=Compute Cluster, IPA=Instance Pool, SA=Stand Alone Instances: ")
                if choice_cluster_type.lower() in ['cn','cc','ipa','ip','sa']:
                    cluster_type = choice_cluster_type.upper()
                    break
                else:
                    logger.info(f"Invalid choice {choice_cluster_type}")
    
    if instance_config_ocid and count:
        logger.info(f"Creating cluster with {count} nodes and instance configuration {instance_config_ocid}")
        instance_config_details = mgmt_utils.get_instance_config_details(instance_config_ocid)
        if instance_config_details is None:
            logger.error(f"The instance configuration with OCID {instance_config_ocid} was not found")
            exit()
        if args.create_cluster_subnet:
            subnet_id=args.create_cluster_subnet
        else:
            subnet_id=instance_config_details.instance_details.launch_details.create_vnic_details.subnet_id
        mgmt_utils.generate_inventory(instance_config_details,clustername,cluster_type)
        try:
            cluster = mgmt_utils.create_cluster(cluster_type,None,instance_config_ocid,count,compartment_ocid,clustername,availabilitydomain,subnet_id,controller_hostname)
        except Exception as e:
            logger.error(f"Could not create the cluster with error {e}")
            mgmt_utils.remove_inventory(clustername)
    else:
        logger.error(f"There is no instance configuration available for this cluster")

if args.delete_cluster:
    clustername = args.delete_cluster
    logger.info(f"Deleting cluster named {clustername}")
    mgmt_utils.delete_cluster(clustername,compartment_ocid)
    mgmt_utils.remove_inventory(clustername)