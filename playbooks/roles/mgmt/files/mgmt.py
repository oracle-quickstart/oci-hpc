from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
import sys
from mgmt_shared_logging import logger
import argparse
from datetime import datetime, timedelta, timezone
import mgmt_utils 
import json
import time

from node import Node
from cluster import Cluster

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
    specified_node_names = NodeSet(args.nodes)
    logger.info(f"Processing nodes: {specified_node_names}")
else:
    specified_node_names= NodeSet()
    logger.info(f"Processing all nodes")
if args.clusters:
    specified_cluster_names = args.clusters.split(',')
    logger.info(f"Processing Clusters: {specified_cluster_names}")
else:
    specified_cluster_names = []
if specified_node_names and specified_cluster_names:
    logger.error("You cannot provide a hostlist and a clusterlist")
    exit(1)
if args.recom:
    logger.info("Recompute flag is set.")
if args.reboot:
    logger.info("Reboot flag is set.")
    if not specified_node_names and not specified_cluster_names and not args.all :
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the reboot flag")
        exit(1)
if args.image:
    if args.bvr:
        if not specified_node_names and not specified_cluster_names and not args.all:
            logger.error("You need to provide a hostlist, a clusterlist or --all to use the bvr flag")
            exit(1)
        logger.info(f"BVR flag is set with image OCID: {args.image}")
    else:
        logger.error("You need to provide the BVR flag along with the image")
        exit(1)
elif args.bvr:
    if not specified_node_names and not specified_cluster_names and not args.all:
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the bvr flag")
        exit(1)
if args.tag:
    logger.info(f"Tag flag is set")
    if not specified_node_names:
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the tag flag")
        exit(1)
if args.terminate:
    logger.info(f"Terminate flag is set")
    if not specified_node_names and not specified_cluster_names and not args.all:
        logger.error("You need to provide a hostlist, a clusterlist or --all to use the terminate flag")
        exit(1)
if args.all:
    if specified_node_names or specified_cluster_names:
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

oci_clients={"computeClient":computeClient,
             "ComputeClientCompositeOperations": ComputeClientCompositeOperations,
             "computeManagementClient":computeManagementClient,
             "ComputeManagementClientCompositeOperations":ComputeManagementClientCompositeOperations,
             "virtualNetworkClient":virtualNetworkClient,
             "DNSClient":DNSClient,
             "IdentityClient":IdentityClient,
             "IdentityClientCompositeOperations":IdentityClientCompositeOperations
}
nodes = [Node(entry,oci_clients) for entry in results]

controller = [i for i in nodes if i.role == "controller"]

if len(controller) > 1:
    logger.error(f"There are multiple controller in the DB, Using {controller[0]['hostname']}")
 
controller_hostname=controller[0].hostname
compartment_ocid=controller[0].compartment

login = [i for i in nodes if i.role == "login"]

clusters=[]
for node in nodes:
    if node.role != "login" and node.role != "controller":
        added=False
        for cluster in clusters:
            if node.cluster_name == cluster.cluster_name:
                cluster.addNodeToList(node)
                added=True
        if not added:
            clusters.append(Cluster(node.cluster_name,[node],oci_clients))

if args.create_cluster:
    if args.create_cluster in [cluster.cluster_name for cluster in clusters]:
        logger.error("You are trying to create a cluster with a name that already exists, this will add confusion. Please rename")
        exit(1)

if specified_node_names:
    compute=[]
    compute_with_terminated = [] # Cannot show terminated nodes with nodes list of cluster defined, only -a
    for nodename in specified_node_names:
        if nodename in [i.hostname for i in nodes] or nodename in [i.ip_address for i in nodes] or nodename in [i.oci_name for i in nodes]:
            compute+=[i for i in nodes if (i.hostname == nodename or i.ip_address == nodename or i.oci_name == nodename)]
        else:
            logger.error(f"Node: {nodename} is not present in the DB")
elif specified_cluster_names:
    compute=[]
    for clustername in specified_cluster_names:
        for cluster in clusters:
            if cluster.cluster_name == clustername:
                compute+=cluster.nodeList
        if not compute:
            logger.error(f"Cluster: {clustername} has no matching nodes present in the DB")
    specified_node_names=NodeSet(','.join([node.hostname for node in compute]))
else:
    compute_with_terminated=[node for node in nodes if node.role == "compute" or node.controller_status == "waiting_for_info"]
    compute=[node for node in nodes if (node.role == "compute" or node.controller_status == "waiting_for_info") and (node.status != "terminated")]

for node in compute:
    if node.controller_status == "configured" and node.compute_status == "configured":
        configured_nodes.append(node)
    elif node.compute_status == "configuring":
        waiting_for_compute.append(node)
    elif node.controller_status == "terminating":
        terminating.append(node)
    elif node.controller_status == "waiting_for_info":
        startedTime = datetime.strptime(node.startedTime, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if startedTime < timeTH:
            failing_starting.append(node)
        starting.append(node)
    if node.controller_status == "configured" and node.compute_status in ["configured", "configuring"]:
        lastTimeReachable = datetime.strptime(node.lastTimeReachable, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if lastTimeReachable < timeTH:
            unreachable_nodes.append(node)
    if node.healthcheck_recomandation == "Reboot":
        hc_reboot.append(node)
    elif node.healthcheck_recomandation == "Terminate":
        hc_terminate.append(node)

logger.info(f"Counts: Configured: {len(configured_nodes)}, Configuring: {len(waiting_for_compute)}, "
            f"Starting: {len(starting)}, Terminating: {len(terminating)}")

logger.info(f"Configured Nodes: {NodeSet(','.join([node.hostname for node in configured_nodes]))}")
logger.info(f"Configuring Nodes: {NodeSet(','.join([node.hostname for node in waiting_for_compute]))}")
logger.info(f"Terminating Nodes: {NodeSet(','.join([node.hostname for node in terminating]))}")
logger.info(f"Starting Nodes: {','.join([node.ip_address for node in starting])}")
logger.info(f"Healthcheck Recommendations to Reboot: {NodeSet(','.join([node.hostname for node in hc_reboot]))}")
logger.info(f"Healthcheck Recommendations to Terminate: {NodeSet(','.join([node.hostname for node in hc_terminate]))}")

logger.info("Clusters: "+','.join([cluster.cluster_name for cluster in clusters]))
logger.info(f"Login Nodes: {NodeSet(','.join([node.hostname for node in login]))}")

if failing_starting:
    logger.warning(f"Some nodes are failing to start: {','.join([node.ip_address for node in failing_starting])}")
if unreachable_nodes:
    logger.warning(f"Some nodes haven't responded in a while: {','.join([node.ip_address for node in unreachable_nodes])}")

if args.details:
    if args.all:
        for node in compute_with_terminated:
            node.print_dict()
    else:
        for node in compute:
            node.print_dict()


if failing_starting or unreachable_nodes or hc_reboot or hc_terminate:
    if args.recom:
        ocids=[]
        for node in unreachable_nodes + hc_reboot:
            node.reboot()
        if failing_starting:
            logger.info(f"Restarting the configuration script on: {NodeSet(','.join([node.ip_address for node in failing_starting]))}")
            task = task_self()
            task.shell("/config/compute.sh", nodes=NodeSet(','.join([node.ip_address for node in failing_starting])))
            task.run()
            logger.info(f"Reconfiguration is done, logs are available at /config/logs/")
        for node in hc_terminate:
            node.tag_unhealthy()
            node.terminate()
    else:
        if failing_starting:
            logger.warning("If you would like to reconfigure the starting nodes, rerun this script with --recomm")
        if unreachable_nodes:
            logger.warning("If you would like to reboot the unreachables nodes, rerun this script with --recomm")
        if hc_reboot or hc_terminate:
            logger.warning("If you would like to reboot or terminate based on healthcheck results, rerun this script with --recomm")

if args.reboot:
    for node in compute:
        node.reboot()

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
    for node in compute:        
        logger.info(f"Replacing BV for instance: "+instance["hostname"])
        node.bvr(image_ocid)
        count +=1
        if count > parallelism:
            logger.info(f"Taking a break after {parallelism} instances")
            time.sleep(30)
            count = 0

if args.tag:
    for node in compute:
        node.tag_unhealthy()
        
if args.configure:
    config_list=[]
    for node_name in specified_node_names:
        for node in compute:
            if node_name == node.hostname or node_name == node.oci_name or node_name == node.ip_address:
                config_list.append(node)
    logger.info(f"Restarting the configuration script on: {NodeSet(','.join(specified_node_names))}")
    task = task_self()
    task.shell("sudo /config/cloud-init.sh", nodes=NodeSet(','.join([node.ip_address for i in config_list])))
    task.run()
    logger.info(f"Reconfiguration is done, logs are available at /config/logs/")

if args.terminate:
    for node in compute:
        node.terminate()

if args.add:
    cluster_to_add = None
    if len(specified_cluster_names)==0:
        logger.info(f"No Cluster was defined to add")
        if len(clusters) == 1:
            cluster_to_add=clusters[0]
            logger.info(f"Using the 1 clustername found: {cluster_to_add.cluster_name}")
        else:
            logger.error(f"There were {len(clusters)} clusters found and none specified, specify one of the cluster")
            for i, cluster in enumerate(clusters):
                print(f"{i+1}. {cluster.cluster_name}")
            choice_config = int(input("Enter the number of the cluster to use: ")) - 1
            cluster_to_add=clusters[choice_config]
    elif len(specified_cluster_names)>1:
        logger.error(f"Only Specify one cluster for resize")
    elif len(specified_cluster_names)==1:
        for cluster in clusters:
            if cluster.cluster_name == specified_cluster_names[0]:
                cluster_to_add=cluster
    if not cluster_to_add is None:
        logger.info(f"Adding a node to: {cluster_to_add.cluster_name}")
        cluster_to_add.add(args.add)

if args.create_cluster:
    clustername = args.create_cluster

    # Get how the cluster details will be given:
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

    # Get the Number of nodes for the cluster
    if args.create_cluster_count:
        count = args.create_cluster_count
    else:
        # Ask user to choose a custom image
        choice = int(input("How many nodes need to be created in the cluster: "))
        count = choice

    #Get the AD
    availabilitydomains = mgmt_utils.guess_availabilitydomain(compartment_ocid)
    if len(availabilitydomains)==1:
        availabilitydomain=availabilitydomains[0]
    elif args.create_cluster_ad:
        availabilitydomain=args.create_cluster_ad
    elif args.create_cluster_instance_type is None:
        for i, ad in enumerate(availabilitydomains):
            print(f"{i+1}. {ad} ")
            choice_ad = int(input("Enter the AD index: ")) - 1
            availabilitydomain=choice_ad
            logger.info(f"This AD was chosen {availabilitydomain}")
    else:
        availabilitydomain=None

    # In case instance type was selected (Using queues.conf as a reference)
    if args.create_cluster_instance_type or not instance_type is None:
        if instance_type is None:
            instance_type_found=mgmt_utils.get_instance_type(args.create_cluster_instance_type)
            if instance_type_found is None:
                logger.error(f"The Instance type {args.create_cluster_instance_type} does not exists in /opt/oci-hpc/conf/queues.conf")
                exit(1)
            else:
                instance_type=instance_type_found
        availabilitydomains=instance_type["ad"]
        subnet_id=instance_type["private_subnet_id"]
        targetCompartment=instance_type["targetCompartment"]

        if instance_type["stand_alone"]:
            if instance_type["rdma_enabled"]:
                cluster_type="CC"
            else:
                cluster_type="SA"
        else:
            if instance_type["rdma_enabled"]:
                cluster_type="CN"
            else:
                cluster_type="IPA"

    # In case instance OCID was selected
    elif args.create_cluster_inst_config or not instance_config_ocid is None:
        targetCompartment=compartment_ocid

        if args.create_cluster_inst_config:
            instance_config_ocid = args.create_cluster_inst_config
        
        if args.create_cluster_subnet:
            subnet_id=args.create_cluster_subnet
        else:
            subnet_id=None

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
    

    cluster=Cluster(clustername,[],oci_clients)
    cluster.create(cluster_type,instance_type,instance_config_ocid,count,compartment_ocid,availabilitydomain,subnet_id,controller_hostname)

if args.delete_cluster:
    clustername = args.delete_cluster
    for cluster in clusters:
        if cluster.cluster_name == clustername:
            cluster.delete()