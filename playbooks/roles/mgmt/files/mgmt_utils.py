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

def force_reboot(ocid):
    computeClient.instance_action(instance_id=ocid,action="RESET")

def instance_bvr(instance_ocid,image_ocid):
    update_instance_source_details = oci.core.models.UpdateInstanceSourceViaImageDetails()
    update_instance_source_details.image_id = image_ocid
    update_instance_source_details.is_preserve_boot_volume_enabled = False
    update_instance_source_details.is_force_stop_enabled = True
    update_instance_details = oci.core.models.UpdateInstanceDetails()
    update_instance_details.source_details = update_instance_source_details
    ComputeClientCompositeOperations.update_instance_and_wait_for_state(instance_ocid, update_instance_details,wait_for_states=["STOPPING","STOPPED","STARTING","RUNNING"])

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
def terminate_instance(nodename, instance, instance_ocid, compartment_ocid):
    try:
        ipa_ocid,ipa_type=get_ipa_ocid(instance, compartment_ocid)
        if ipa_type == "StandAlone" or ipa_type == "CC":
            logger.info("Terminating node: "+nodename+" with details "+instance["hostname"]+", "+instance["oci_name"]+", "+instance["ip_address"])
            ComputeClientCompositeOperations.terminate_instance_and_wait_for_state(instance_ocid,wait_for_states=["TERMINATING","TERMINATED"])
        elif ipa_type == "IPA" or ipa_type == "CN":
            logger.info("Terminating node: "+nodename+" with details "+instance["hostname"]+", "+instance["oci_name"]+", "+instance["ip_address"])
            instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=instance_ocid,is_auto_terminate=True,is_decrement_size=True)
            ComputeManagementClientCompositeOperations.detach_instance_pool_instance_and_wait_for_work_request(ipa_ocid,instance_details)
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error: {e}")

def tag_unhealthy(node,instance_ocid):
    instance = computeClient.get_instance(instance_id=instance_ocid).data
    tags = instance.defined_tags
    tags.update({'ComputeInstanceHostActions': { 'CustomerReportedHostStatus': 'unhealthy' }})
    update_instance_details = oci.core.models.UpdateInstanceDetails(defined_tags=tags)
    logger.info("Updating tags on instance: "+node+" with OCID:"+instance_ocid)
    try:
        update_instance_response = ComputeClientCompositeOperations.update_instance_and_wait_for_state(instance_ocid, update_instance_details,wait_for_states=["RUNNING"])
    except oci.exceptions.ServiceError as e:
        logger.error("The tag does not exists or the controller doesn't have acces to the tag")
        logger.error("Make sure the Tag namespace ComputeInstanceHostActions exists with the defined tag: CustomerReportedHostStatus")

def get_ipa_ocid(instance, compartment_ocid):
    if instance["cluster_name"]:
        instance_pools = oci.pagination.list_call_get_all_results(computeManagementClient.list_cluster_networks,compartment_ocid,display_name=instance["cluster_name"]).data
        if len(instance_pools):
            for instance_pool in instance_pools:
                 ipa_ocid=instance_pool.instance_pools[0].id
                 instance_summaries = oci.pagination.list_call_get_all_results(computeManagementClient.list_instance_pool_instances,compartment_ocid,ipa_ocid).data
                 for instance_summary in instance_summaries:
                    if instance["ocid"]:
                        if instance_summary.id == instance["ocid"]:
                            return ipa_ocid,"CN"
                    else:
                        if instance_summary.lifecycle_state == "TERMINATED":
                            continue
                        try:
                            for potential_vnic_attachment in oci.pagination.list_call_get_all_results(computeClient.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=instance_summary.id).data:
                                if potential_vnic_attachment.display_name is None:
                                    vnic_attachment = potential_vnic_attachment
                            vnic = virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                            if vnic.private_ip == instance["ip_address"]:
                                return ipa_ocid,"CN"
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
                instance_summaries = computeClient.list_instances(compartment_ocid,compute_cluster_id=instance_pool.id).data
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

def query_db():
    try:
        # DB Connection Details
        db_host = "localhost"
        db_user = "clusterUser"
        db_pw = "Cluster1234!"
        db_name = "clusterDB"
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
    cn_summaries = computeManagementClient.list_cluster_networks(compartment_ocid,display_name=clustername).data
    if len(cn_summaries) > 0:
        for cn_summary_tmp in cn_summaries:
            if cn_summary_tmp.lifecycle_state == "RUNNING":
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
        for cn_summary_tmp in cn_summaries:
            if cn_summary_tmp.lifecycle_state == "ACTIVE" and cn_summary_tmp.display_name == clustername :
                running_clusters = running_clusters + 1
                running_clusters_info.append([cn_summary_tmp,"CC"])

    # Looking for IPAs
    cn_summaries = computeManagementClient.list_instance_pools(compartment_ocid,display_name=clustername).data
    if len(cn_summaries) > 0:
        for cn_summary_tmp in cn_summaries:
            if cn_summary_tmp.id in [i[0].instance_pools[0].id for i in running_clusters_info if i[1] == "CN"]:
                # Ignore matching IPAs for existing CNs
                continue
            else:
                if cn_summary_tmp.lifecycle_state == "RUNNING":
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
    elif running_clusters == 1:
        cn_summary = running_clusters_info[0][0]
        CN=running_clusters_info[0][1]
    elif running_clusters > 1:
        logger.info("There were multiple running clusters with this name")
        for i, cluster in enumerate(running_clusters_info):
            print(f"{i+1}. {cluster[0].id} of type {cluster[1]}")
        # Ask user to choose which cluster to scale
        choice = int(input("Enter the number of the cluster use: ")) - 1
        cn_summary = running_clusters_info[choice][0]
        CN=running_clusters_info[choice][1]

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

def getLaunchInstanceDetailsFromInstance(instance,compartment_ocid,cn_ocid,clustername):

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
    if instance.shape.startswith("BM"):
        launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=instance.availability_domain, compartment_id=compartment_ocid,compute_cluster_id=cn_ocid,shape=instance.shape,source_details=instance.source_details,metadata=instance.metadata,display_name=new_display_name,freeform_tags=instance.freeform_tags,create_vnic_details=create_vnic_details)
    else:
        launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=instance.availability_domain, compartment_id=compartment_ocid,compute_cluster_id=cn_ocid,shape=instance.shape,shape_config=launchInstanceShapeConfigDetails,source_details=instance.source_details,metadata=instance.metadata,display_name=new_display_name,freeform_tags=instance.freeform_tags,create_vnic_details=create_vnic_details)
    return launch_instance_details
def getLaunchInstanceDetailsFromInstanceType(instance_type,subnet_id,clustername,controller_hostname,cn_id):

    if subnet_id is None:
        subnet_id=instance_type['private_subnet_id']
    image_id=instance_type['image']
    bv_size=instance_type['boot_volume_size']
    availability_domain=instance_type['ad']
    targetCompartment=instance_type['targetCompartment']
    shape=instance_type['shape']
    availability_domain=instance_type['ad']
    cpus=instance_type['instance_pool_ocpus']
    memory=instance_type['instance_pool_memory']
    hostname_convention=instance_type['hostname_convention']
    RDMA=instance_type['cluster_network']
    ### Not working yet
    mkplace=instance_type['use_marketplace_image']
    marketplace_listing=instance_type['marketplace_listing']

    with open("/config/key/public", "r") as file:
        public_key = file.read()
    with open("/config/cloud-init.sh", "r") as file:
        cloud_init = base64.b64encode(file.read().encode()).decode()

    """
    Creates a new instance configuration by fully replicating the source configuration.
    If a new SSH key is provided, it replaces the SSH key in the launch metadata.
    """
    try:

        if RDMA:
            plugins_config_definition=[
                oci.core.models.InstanceAgentPluginConfigDetails(
                    desired_state="ENABLED",
                    name="Compute HPC RDMA Authentication"
                ),
                oci.core.models.InstanceAgentPluginConfigDetails(
                    desired_state="ENABLED",
                    name="Compute HPC RDMA Auto-Configuration"
                ),
                oci.core.models.InstanceAgentPluginConfigDetails(
                    desired_state="ENABLED",
                    name="Compute RDMA GPU Monitoring"
                ),
            ]
        else:
            plugins_config_definition=[]

        new_agent_config = oci.core.models.LaunchInstanceAgentConfigDetails(
            are_all_plugins_disabled=False,
            is_monitoring_disabled=False,
            plugins_config=plugins_config_definition
        )


        new_create_vnic = oci.core.models.CreateVnicDetails(
            assign_public_ip=False,
            subnet_id=subnet_id
            # Additional fields can be added here if needed
        )

        new_source_details = oci.core.models.InstanceSourceViaImageDetails(
            source_type="image",
            image_id=image_id,
            boot_volume_size_in_gbs=int(bv_size),
            boot_volume_vpus_per_gb=int(30)
        )

        new_metadata={"ssh_authorized_keys":public_key,"user_data": cloud_init}
        new_tags={"cluster_name" : clustername, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}

        if shape.endswith("Flex"):
            new_launch_details = oci.core.models.LaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=targetCompartment,
            shape=shape,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=cpus,memory_in_gbs=memory),
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details,
            compute_cluster_id=cn_id
            )
        else:
            new_launch_details = oci.core.models.LaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=targetCompartment,
            shape=shape,
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details,
            compute_cluster_id=cn_id
            ) 
        return new_launch_details
    except oci.exceptions.ServiceError as e:
        logger.error(f"An error occurred: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

def getLaunchInstanceDetailsFromInstanceConfig(instance_config_ocid,compartment_ocid,cn_ocid,availability_domain,clustername,subnet_id,controller_hostname):

    instance_config=get_instance_config_details(instance_config_ocid)
    agent_config=instance_config.instance_details.launch_details.agent_config
    agent_config.__class__ = oci.core.models.LaunchInstanceAgentConfigDetails
    createVnicDetails=instance_config.instance_details.launch_details.create_vnic_details
    createVnicDetails.__class__ = oci.core.models.CreateVnicDetails
    createVnicDetails.subnet_id=subnet_id
    shape=instance_config.instance_details.launch_details.shape
    shape_config=instance_config.instance_details.launch_details.shape_config
    if shape_config is None:
        launchInstanceShapeConfigDetails=None
    else:
        try:
            nvmes=shape_config.local_disks
            launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,nvmes=nvmes,ocpus=shape_config.ocpus)
        except:
            launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,ocpus=shape_config.ocpus)
    source_details=instance_config.instance_details.launch_details.source_details
    source_details.__class__ = oci.core.models.InstanceSourceViaImageDetails
    metadata=instance_config.instance_details.launch_details.metadata
    new_tags=instance_config.instance_details.launch_details.freeform_tags
    new_tags["cluster_name"] = clustername
    if not 'controller_name' in new_tags.keys():
        new_tags['controller_name'] = controller_hostname

    defined_tags=instance_config.instance_details.launch_details.defined_tags

    new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+clustername
    if shape_config is None:
        launch_instance_details=oci.core.models.LaunchInstanceDetails(
        agent_config=agent_config,
        availability_domain=availability_domain, 
        compartment_id=compartment_ocid,
        compute_cluster_id=cn_ocid,
        shape=shape,
        source_details=source_details,
        metadata=metadata,
        display_name=new_display_name,
        freeform_tags=new_tags,
        defined_tags=defined_tags,
        create_vnic_details=createVnicDetails
        )
        
    else:
        try:
            nvmes=shape_config.local_disks
            launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,nvmes=nvmes,ocpus=shape_config.ocpus)
        except:
            launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,ocpus=shape_config.ocpus)

        launch_instance_details=oci.core.models.LaunchInstanceDetails(
            agent_config=agent_config,
            availability_domain=availability_domain, 
            compartment_id=compartment_ocid,
            compute_cluster_id=cn_ocid,
            shape=shape,
            shape_config=launchInstanceShapeConfigDetails,
            source_details=source_details,
            metadata=metadata,
            display_name=new_display_name,
            freeform_tags=new_tags,
            defined_tags=defined_tags,
            create_vnic_details=createVnicDetails
            )
    return launch_instance_details

def add_node_to_cluster(clustername,number_of_nodes,compartment_ocid):

    cn_summary,ip_summary,CN = get_summary(compartment_ocid,clustername)
    if CN == "CC":
        logger.info(cn_summary.id+" "+CN)
    else:
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
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(instance,compartment_ocid,cn_summary.id,clustername)
                    ComputeClientCompositeOperations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
        else:
            current_size=ip_summary.size
            size = ip_summary.size + number_of_nodes
            update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
            logger.info(f"Launching {number_of_nodes} in the Compute Cluster for a total size of {size}")
            ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(ip_summary.id,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
        cn_summary,ip_summary,CN = get_summary(compartment_ocid,clustername)
        new_cn_instances = get_instances(compartment_ocid,cn_summary.id,CN)
        newsize=len(new_cn_instances)
        if newsize == current_size:
            logger.error("No node was added, please check the work requests of the Cluster Network and Instance Pool to see why")
            exit(1)

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

def generate_instance_config(instance_type,controller_hostname,clustername):
    subnet_id=instance_type['private_subnet_id']
    image_id=instance_type['image']
    bv_size=instance_type['boot_volume_size']
    availability_domain=instance_type['ad']
    targetCompartment=instance_type['targetCompartment']
    shape=instance_type['shape']
    availability_domain=instance_type['ad']
    cpus=instance_type['instance_pool_ocpus']
    memory=instance_type['instance_pool_memory']
    hostname_convention=instance_type['hostname_convention']
    RDMA=instance_type['cluster_network']
    ### Not working yet
    mkplace=instance_type['use_marketplace_image']
    marketplace_listing=instance_type['marketplace_listing']

    with open("/config/key/public", "r") as file:
        public_key = file.read()
    with open("/config/cloud-init.sh", "r") as file:
        cloud_init = base64.b64encode(file.read().encode()).decode()

    """
    Creates a new instance configuration by fully replicating the source configuration.
    If a new SSH key is provided, it replaces the SSH key in the launch metadata.
    """
    try:

        if RDMA:
            plugins_config_definition=[
                oci.core.models.InstanceAgentPluginConfigDetails(
                    desired_state="ENABLED",
                    name="Compute HPC RDMA Authentication"
                ),
                oci.core.models.InstanceAgentPluginConfigDetails(
                    desired_state="ENABLED",
                    name="Compute HPC RDMA Auto-Configuration"
                ),
                oci.core.models.InstanceAgentPluginConfigDetails(
                    desired_state="ENABLED",
                    name="Compute RDMA GPU Monitoring"
                ),
            ]
        else:
            plugins_config_definition=[]

        new_agent_config = oci.core.models.InstanceConfigurationLaunchInstanceAgentConfigDetails(
            are_all_plugins_disabled=False,
            is_monitoring_disabled=False,
            plugins_config=plugins_config_definition
        )


        new_create_vnic = oci.core.models.InstanceConfigurationCreateVnicDetails(
            assign_public_ip=False,
            subnet_id=subnet_id
            # Additional fields can be added here if needed
        )

        new_source_details = oci.core.models.InstanceConfigurationInstanceSourceViaImageDetails(
            source_type="image",
            image_id=image_id,
            boot_volume_size_in_gbs=int(bv_size),
            boot_volume_vpus_per_gb=int(30)
        )

        new_metadata={"ssh_authorized_keys":public_key,"user_data": cloud_init}
        new_tags={"cluster_name" : clustername, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}

        if shape.endswith("Flex"):
            new_launch_details = oci.core.models.InstanceConfigurationLaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=targetCompartment,
            shape=shape,
            shape_config=oci.core.models.InstanceConfigurationLaunchInstanceShapeConfigDetails(ocpus=cpus,memory_in_gbs=memory),
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details
            )
        else:
            new_launch_details = oci.core.models.InstanceConfigurationLaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=targetCompartment,
            shape=shape,
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details
            ) 


        # Build new Instance Details
        new_instance_details = oci.core.models.ComputeInstanceDetails(
            instance_type="compute",
            launch_details=new_launch_details
        )

        # Construct new Instance Configuration Details object
        new_config_details = oci.core.models.CreateInstanceConfigurationDetails(
            compartment_id=targetCompartment,
            display_name= clustername,
            instance_details=new_instance_details
        )

        create_response = computeManagementClient.create_instance_configuration(new_config_details).data
        # Check that the instance config can be queried.
        for i in range(10):
            try:
                get_response=computeManagementClient.get_instance_configuration(create_response.id).data
            except:
                time.sleep(3)
                continue
        return create_response

    except oci.exceptions.ServiceError as e:
        logger.error(f"An error occurred: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

def get_instance_config_details(instance_config_ocid):
    try:
        instance_configuration=computeManagementClient.get_instance_configuration(instance_config_ocid).data
        return instance_configuration
    except:
        return None
def create_cluster(cluster_type,instance_type,instance_config_ocid,count,compartment_ocid,clustername,availability_domain,subnet_id,controller_hostname):
    if cluster_type == "CN":
        ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=subnet_id)
        ip_placement_details=oci.core.models.ClusterNetworkPlacementConfigurationDetails(availability_domain=availability_domain,primary_vnic_subnets=ip_placement_subnet_details)
        instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails(display_name=clustername,instance_configuration_id=instance_config_ocid,size=count)
        cn_details=oci.core.models.CreateClusterNetworkDetails(compartment_id=compartment_ocid,display_name=clustername,instance_pools=[instance_pools_details],placement_configuration=ip_placement_details)
        cn = ComputeManagementClientCompositeOperations.create_cluster_network_and_wait_for_state(create_cluster_network_details=cn_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})
        return cn.data
    elif cluster_type == "IP" or cluster_type == "IPA":
        ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=subnet_id)
        ip_placement_details=oci.core.models.CreateInstancePoolPlacementConfigurationDetails(availability_domain=availability_domain,primary_vnic_subnets=ip_placement_subnet_details)
        instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails()
        ip_details=oci.core.models.CreateInstancePoolDetails(compartment_id=compartment_ocid,display_name=clustername,placement_configurations=[ip_placement_details],instance_configuration_id=instance_config_ocid,size=count)
        cn = ComputeManagementClientCompositeOperations.create_instance_pool_and_wait_for_state(create_instance_pool_details=ip_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})
        return cn.data
    elif cluster_type == "CC":
        cc_details=oci.core.models.CreateComputeClusterDetails(compartment_id=compartment_ocid,availability_domain=availability_domain,display_name=clustername)
        cn = computeClient.create_compute_cluster(create_compute_cluster_details=cc_details).data
        for i in range(count):
            if instance_type is None:
                launch_instance_details = getLaunchInstanceDetailsFromInstanceConfig(instance_config_ocid,compartment_ocid,cn.id,availability_domain,clustername,subnet_id,controller_hostname)
            else:
                launch_instance_details = getLaunchInstanceDetailsFromInstanceType(instance_type,subnet_id,clustername,controller_hostname,cn.id)
            ComputeClientCompositeOperations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
        return get_instances(compartment_ocid,cn.id,cluster_type)
    
def generate_inventory(instance_config_details,clustername,cluster_type):
    original_inventory="/config/playbooks/inventory"
    inventory_name=f"/config/playbooks/inventory_{clustername}"
    try:
        hostname_convention = instance_config_details.instance_details.launch_details.freeform_tags["hostname_convention"]
    except:
        hostname_convention=""
    modifications={"cluster_name":clustername,
                   "shape":instance_config_details.instance_details.launch_details.shape,
                   "cluster_network":"true" if cluster_type in ["CN","CC"] else "false",
                   "hostname_convention": hostname_convention
                   }
    try:
        with open(original_inventory, 'r') as file:
            lines = file.readlines()

        with open(inventory_name, 'w') as file:
            for line in lines:
                for key, new_value in modifications.items():
                    if re.match(rf"^{key}=", line.strip()):  # Match exact key
                        line = f"{key}={new_value}\n"
                file.write(line)

        logger.info("Inventory file updated successfully!")

    except FileNotFoundError:
        logger.error("The inventory file was not found.")
    except Exception as e:
        logger.error(f"{e}")
    return inventory_name

def remove_inventory(clustername):
    inventory_name=f"/config/playbooks/inventory_{clustername}"
    if os.path.exists(inventory_name):
        os.remove(inventory_name)
        logger.info(f"Inventory {inventory_name} deleted successfully.")
    else:
        logger.warning(f"Inventory {inventory_name} was not present.")

def delete_cluster(clustername,compartment_ocid):
    cn_summary,ip_summary,CN = get_summary(compartment_ocid,clustername)
    if CN == "CN":
        computeManagementClient.terminate_cluster_network(cn_summary.id)
    elif CN == "IPA":
        computeManagementClient.terminate_instance_pool(cn_summary.id)
    elif CN == "CC" or "SA":
        cn_instances = get_instances(compartment_ocid,cn_summary.id,CN)
        for instance in cn_instances:
            ComputeClientCompositeOperations.terminate_instance_and_wait_for_state(instance['ocid'],wait_for_states=["TERMINATING","TERMINATED"])
        instance_running=True
        while instance_running:
            instance_running=False
            for instance in cn_instances:
                if computeClient.get_instance(instance['ocid']).data.lifecycle_state != "TERMINATED":
                    instance_running=True
                    time.sleep(30)
        if CN == "CC":
            computeClient.delete_compute_cluster(cn_summary.id)

def guess_availabilitydomain(compartment_ocid):
    ads=IdentityClient.list_availability_domains(compartment_ocid).data
    return [i.name for i in ads]

def list_subnets(compartment_ocid):
    return virtualNetworkClient.list_subnets(compartment_id=compartment_ocid).data