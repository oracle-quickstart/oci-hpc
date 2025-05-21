from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self

from lib.database import db_create_node, get_nodes_by_id, db_update_node

from lib.logger import logger
import sys, os
import random, string, re, base64
import time

from datetime import datetime, timedelta, timezone
version = sys.version_info
if version >= (3, 12):
    UTC = timezone.utc

inventory_path="/config/playbooks/inventory"

try:
    import oci
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    compute_client = oci.core.ComputeClient(config={}, signer=signer)
    compute_client_composite_operations= oci.core.ComputeClientCompositeOperations(compute_client)
    compute_management_client = oci.core.ComputeManagementClient(config={}, signer=signer)
    compute_management_client_composite_operations = oci.core.ComputeManagementClientCompositeOperations(compute_management_client)
    virtual_network_client = oci.core.VirtualNetworkClient(config={}, signer=signer)
    dns_client = oci.dns.DnsClient(config={}, signer=signer)
    identity_client= oci.identity.IdentityClient(config={}, signer=signer)
    identity_client_composite_operations= oci.identity.IdentityClientCompositeOperations(identity_client)

    queue_admin_client = oci.queue.QueueAdminClient(config={}, signer=signer)

except ImportError:
    sys.exit(1)

def list_custom_images(compartment_ocid):
    try:
        response = oci.pagination.list_call_get_all_results(compute_client.list_images,compartment_id=compartment_ocid)
        custom_images=[]
        if response.data:
            for image in response.data:
                custom_images.append(image)
        else:
            logger.info(f"No custom images found in compartment {compartment_ocid}.")
    except oci.exceptions.ServiceError as e:
         logger.error(f"Error retrieving custom images: {compartment_ocid}")
    for i, img in enumerate(custom_images):
        print(f"{i+1}. {img.display_name} ({img.id})")
    # Ask user to choose a custom image
    choice = int(input("Enter the number of the custom image to use: ")) - 1
    image_ocid = custom_images[choice].id
    return image_ocid

def run_boot_volume_swap(node,image_ocid):
    update_instance_source_details = oci.core.models.UpdateInstanceSourceViaImageDetails()
    update_instance_source_details.image_id = image_ocid
    update_instance_source_details.is_preserve_boot_volume_enabled = False
    update_instance_source_details.is_force_stop_enabled = True
    update_instance_details = oci.core.models.UpdateInstanceDetails()
    update_instance_details.source_details = update_instance_source_details
    compute_client_composite_operations.update_instance_and_wait_for_state(node.ocid, update_instance_details,wait_for_states=["STOPPING","STOPPED","STARTING","RUNNING"])
          
def run_terminate(node):
    cluster_type,cluster_ocid,instance_pool_ocid = get_instance_type(node)
    try:
        if cluster_type == "SA" or cluster_type == "CC":
            logger.info(f"Terminating node with details {node.hostname}, {node.oci_name}, {node.ip_address}")
            compute_client_composite_operations.terminate_instance_and_wait_for_state(node.ocid,wait_for_states=["TERMINATING","TERMINATED"])
        elif cluster_type == "IPA" or cluster_type == "CN":
            logger.info(f"Terminating node with details {node.hostname}, {node.oci_name}, {node.ip_address}")
            instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=node.ocid,is_auto_terminate=True,is_decrement_size=True)
            compute_management_client_composite_operations.detach_instance_pool_instance_and_wait_for_work_request(instance_pool_ocid,instance_details)
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error: {e}")

def run_reboot(node,soft):
    if soft:
        logger.info("Soft Rebooting: "+str(node.hostname)+" with oci name "+str(node.oci_name)+" with IP "+str(node.ip_address)+" and OCID:"+str(node.ocid))
        compute_client.instance_action(instance_id=node.ocid,action="SOFTRESET")
    else:
        logger.info("Force Rebooting: "+str(node.hostname)+" with oci name "+str(node.oci_name)+" with IP "+str(node.ip_address)+" and OCID:"+str(node.ocid))
        compute_client.instance_action(instance_id=node.ocid,action="RESET")

def run_tag(node):
    instance = compute_client.get_instance(instance_id=node.ocid).data
    tags = instance.defined_tags
    tags.update({'ComputeInstanceHostActions': { 'CustomerReportedHostStatus': 'unhealthy' }})
    update_instance_details = oci.core.models.UpdateInstanceDetails(defined_tags=tags)
    logger.info("Updating tags on instance: "+node.hostname+" with OCID:"+node.ocid)
    try:
        compute_client_composite_operations.update_instance_and_wait_for_state(node.ocid, update_instance_details,wait_for_states=["RUNNING"])
    except oci.exceptions.ServiceError as e:
        logger.error("The tag does not exists or the controller doesn't have acces to the tag")
        logger.error("Make sure the Tag namespace ComputeInstanceHostActions exists with the defined tag: CustomerReportedHostStatus")

def run_add(nodes,count, names):
    if not nodes:
        logger.error("The resize script cannot work for a cluster if the size is there is no node in the cluster")
        exit(1)
    first_node=nodes[0]
    for node in nodes:
        first_node=node
        break

    cluster_type,cluster_ocid,instance_pool_ocid = get_instance_type(first_node)
    current_size=get_instance_count(cluster_type,cluster_ocid,first_node.compartment,first_node.cluster_name)
    target_size = current_size + count
    if cluster_type == "CC" or cluster_type == "SA":
        first_instance=compute_client.get_instance(first_node.ocid).data
        logger.info(f"Launching {count} in the Cluster")
        for i in range(count):
            if cluster_type == "CC":
                if names:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,cluster_ocid,first_node.compartment,first_node.cluster_name,hostname=names[i])
                else:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,cluster_ocid,first_node.compartment,first_node.cluster_name)
            else:
                if names:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,None,first_node.compartment,first_node.cluster_name,hostname=names[i])
                else:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,None,first_node.compartment,first_node.cluster_name)
            compute_client_composite_operations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
    else:
        if names:
            logger.info(f"Host names are ignored for Instance Pools and Cluster Networks")
        update_size = oci.core.models.UpdateInstancePoolDetails(size=target_size)
        logger.info(f"Launching {count} in the Cluster for a total size of {target_size}")
        compute_management_client_composite_operations.update_instance_pool_and_wait_for_state(instance_pool_ocid,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
    newsize=get_instance_count(cluster_type,cluster_ocid,first_node.compartment,first_node.cluster_name)
    logger.info(f"Total number of nodes in the cluster is now {newsize} with a requested size of {target_size}")
    if newsize == current_size:
        logger.error("No node was added, please check the work requests of the Cluster Network and Instance Pool to see why")
        exit(1)

def getLaunchInstanceDetailsFromInstance(first_instance,cluster_ocid,compartment_ocid,cluster_name,hostname=None):

    agent_config=first_instance.agent_config
    agent_config.__class__ = oci.core.models.LaunchInstanceAgentConfigDetails

    for potential_vnic_attachment in oci.pagination.list_call_get_all_results(compute_client.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=first_instance.id).data:
        if potential_vnic_attachment.display_name is None:
            vnic_attachment = potential_vnic_attachment
    create_vnic_details=oci.core.models.CreateVnicDetails(assign_public_ip=False,subnet_id=vnic_attachment.subnet_id)

    shape_config=first_instance.shape_config
    try:
        nvmes=shape_config.local_disks
        if not nvmes:
            raise ValueError("No NVMEs")
        launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,nvmes=nvmes,ocpus=shape_config.ocpus)
    except:
        launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,ocpus=shape_config.ocpus)
    
    freeform_tags=first_instance.freeform_tags
    if hostname is None:
        new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+cluster_name
    else:
        new_display_name=hostname
        if "hostname_convention" in freeform_tags.keys():
            freeform_tags.pop("hostname_convention")
    if first_instance.shape.startswith("BM"):
        launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=first_instance.availability_domain, compartment_id=compartment_ocid,compute_cluster_id=cluster_ocid,shape=first_instance.shape,source_details=first_instance.source_details,metadata=first_instance.metadata,display_name=new_display_name,freeform_tags=freeform_tags,create_vnic_details=create_vnic_details)
    else:
        launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=first_instance.availability_domain, compartment_id=compartment_ocid,compute_cluster_id=cluster_ocid,shape=first_instance.shape,shape_config=launchInstanceShapeConfigDetails,source_details=first_instance.source_details,metadata=first_instance.metadata,display_name=new_display_name,freeform_tags=freeform_tags,create_vnic_details=create_vnic_details)
    return launch_instance_details
    
def get_instance_count(cluster_type,cluster_ocid,compartment_ocid,cluster_name):
    if cluster_type == "SA" or cluster_type == "CC":
        matching_instances=[]
        if cluster_type == "CC":
            instances = oci.pagination.list_call_get_all_results(compute_client.list_instances,compartment_id=compartment_ocid,compute_cluster_id=cluster_ocid,sort_by="TIMECREATED").data
        else:
            instances = oci.pagination.list_call_get_all_results(compute_client.list_instances,compartment_id=compartment_ocid,sort_by="TIMECREATED").data
        for instance in instances:
            if instance.lifecycle_state == "TERMINATED":
                continue
            elif len(instance.freeform_tags) == 0:
                continue
            elif "cluster_name" in instance.freeform_tags.keys():
                if instance.freeform_tags["cluster_name"]!=cluster_name:
                    continue
            matching_instances.append(instance)
        return(len(matching_instances))
    elif cluster_type == "CN":
        instance_summaries = oci.pagination.list_call_get_all_results(compute_management_client.list_cluster_network_instances,compartment_ocid,cluster_ocid,sort_by="TIMECREATED").data
        return(len(instance_summaries))
    elif cluster_type == "IPA":
        instance_summaries = oci.pagination.list_call_get_all_results(compute_management_client.list_instance_pool_instances,compartment_ocid,cluster_ocid,sort_by="TIMECREATED").data
        return(len(instance_summaries))
    
def get_instance_type(node):
    instance_pools = oci.pagination.list_call_get_all_results(compute_management_client.list_cluster_networks,node.compartment,display_name=node.cluster_name).data
    if len(instance_pools):
        for instance_pool in instance_pools:
            ipa_ocid=instance_pool.instance_pools[0].id
            instance_summaries = oci.pagination.list_call_get_all_results(compute_management_client.list_instance_pool_instances,node.compartment,ipa_ocid).data
            for instance_summary in instance_summaries:
                if instance_summary.id == node.ocid:
                    cluster_type="CN"
                    cluster_ocid=instance_pool.id
                    ipa_ocid=ipa_ocid
                    return cluster_type,cluster_ocid,ipa_ocid

    instance_pools = oci.pagination.list_call_get_all_results(compute_management_client.list_instance_pools,node.compartment,display_name=node.cluster_name).data
    if len(instance_pools):
        for instance_pool in instance_pools:
            instance_summaries = oci.pagination.list_call_get_all_results(compute_management_client.list_instance_pool_instances,node.compartment,instance_pool.id).data
            for instance_summary in instance_summaries:
                if instance_summary.id == node.ocid:
                    cluster_type="IPA"
                    cluster_ocid=instance_pool.id
                    ipa_ocid=instance_pool.id
                    return cluster_type,cluster_ocid,ipa_ocid
    try:
        instance_pools = compute_client.list_compute_clusters(node.compartment,display_name=node.cluster_name).data.items
    except:
        logger.warning(f"Compute clusters are not enabled in this region")
        instance_pools = []
    if len(instance_pools):
        for instance_pool in instance_pools:
            instance_summaries = compute_client.list_instances(node.compartment,compute_cluster_id=instance_pool.id).data
            for instance_summary in instance_summaries:
                if instance_summary.id == node.ocid:
                    cluster_type="CC"
                    cluster_ocid=instance_pool.id
                    ipa_ocid=instance_pool.id
                    return cluster_type,cluster_ocid,ipa_ocid
    instance_summaries = oci.pagination.list_call_get_all_results(compute_client.list_instances,compartment_id=node.compartment).data
    for instance_summary in instance_summaries:
        if instance_summary.id == node.ocid:
            cluster_type="SA"
            cluster_ocid=None
            ipa_ocid=None
            return cluster_type,cluster_ocid,ipa_ocid
    logger.warning(f"Node was not found, maybe it is missing tags?")
    return "SA",None

def oci_scan_queue(controller_name):

    queue_ocid=get_queue_ocid()
    endpoint = queue_admin_client.get_queue(queue_ocid).data.messages_endpoint
    queue_client = oci.queue.QueueClient(config={}, signer=signer, service_endpoint=endpoint)
    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
    nodes_to_add=[]
    nodes_to_remove=[]
    while True:
        messages_response = queue_client.get_messages(queue_ocid,limit=20,channel_filter=controller_name)
        if len(messages_response.data.messages) == 0:
            break
        logger.info(f"{len(messages_response.data.messages)} messages found in the queue")

        messages = messages_response.data.messages
        for message in messages:
            try:
                content=eval(message.content)
                if content['status'] == "starting":
                    content['controller_status']="configuring"
                    content['startedTime']=current_time_str
                    nodes_to_add.append(content)
                    db_create_node(content["ocid"], **content)
                    queue_client.delete_message(queue_ocid, message.receipt)
                elif content['status'] == "terminating":
                    node = get_nodes_by_id(NodeSet(content["ocid"]))[0]
                    db_update_node(node,controller_status="terminating",terminatedTime=current_time_str)
                    queue_client.delete_message(queue_ocid, message.receipt)
            except Exception as e:
                print(f"Error evaluating message {message.content}: {e}")

    return nodes_to_add,nodes_to_remove

def get_queue_ocid():
    """
    Parses an Ansible inventory file and returns the value of queue_ocid.

    Args:
        inventory_path (str): Path to the Ansible inventory file.

    Returns:
        str or None: The queue_ocid value, or None if not found.
    """
    queue_ocid = None
    in_vars_section = False

    with open(inventory_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[all:vars]"):
                in_vars_section = True
                continue
            elif line.startswith("[") and in_vars_section:
                # End of [all:vars] block
                break
            if in_vars_section and line.startswith("queue_ocid="):
                queue_ocid = line.split("=", 1)[1].strip()
                break

    return queue_ocid

def get_host_api_dict(compartment,tenancy):
    try:
        compartment_host_api=oci.pagination.list_call_get_all_results(compute_client.list_compute_hosts,compartment_id=compartment).data
    except:
        compartment_host_api=[]
    try:
        tenancy_host_api=oci.pagination.list_call_get_all_results(compute_client.list_compute_hosts,compartment_id=tenancy).data
    except:
        tenancy_host_api=[]
    return compartment_host_api + tenancy_host_api
     

def getLaunchInstanceDetailsFromInstanceType(config, controller_hostname, cn_ocid, cluster_name, hostname=None):

    subnet_id=config.private_subnet_id
    image_id=config.image
    bv_size=config.boot_volume_size
    availability_domain=config.ad
    targetCompartment=config.targetCompartment
    shape=config.shape
    cpus=config.instance_pool_ocpus
    memory=config.instance_pool_memory
    hostname_convention=config.hostname_convention
    RDMA=config.rdma_enabled
    ### Not working yet
    mkplace=config.use_marketplace_image
    marketplace_listing=config.marketplace_listing

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

        if hostname is None:
            new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+cluster_name
            new_tags={"cluster_name" : cluster_name, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}
        else:
            new_display_name=hostname
            new_tags={"cluster_name" : cluster_name, "controller_name" : controller_hostname}

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
            compute_cluster_id=cn_ocid,
            display_name=new_display_name
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
            compute_cluster_id=cn_ocid,
            display_name=new_display_name
            ) 
        return new_launch_details
    except oci.exceptions.ServiceError as e:
        logger.error(f"An error occurred: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

def generate_instance_config(config, controller_hostname, cluster_name):
    subnet_id=config.private_subnet_id
    image_id=config.image
    bv_size=config.boot_volume_size
    availability_domain=config.ad
    targetCompartment=config.targetCompartment
    shape=config.shape
    cpus=config.instance_pool_ocpus
    memory=config.instance_pool_memory
    hostname_convention=config.hostname_convention
    RDMA=config.rdma_enabled
    ### Not working yet
    mkplace=config.use_marketplace_image
    marketplace_listing=config.marketplace_listing

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
        new_tags={"cluster_name" : cluster_name, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}

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
            display_name= cluster_name,
            instance_details=new_instance_details
        )

        create_response = compute_management_client.create_instance_configuration(new_config_details).data
        # Check that the instance config can be queried.
        for i in range(10):
            try:
                create_response=compute_management_client.get_instance_configuration(create_response.id).data
                break
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

def generate_inventory(config,cluster_name):

    original_inventory="/config/playbooks/inventory"
    inventory_name=f"/config/playbooks/inventory_{cluster_name}"
    modifications={"cluster_name":cluster_name,
                "shape":config.shape,
                "rdma_enabled":config.rdma_enabled,
                "hostname_convention": config.hostname_convention
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

def remove_inventory(cluster_name):
    inventory_name=f"/config/playbooks/inventory_{cluster_name}"
    if os.path.exists(inventory_name):
        os.remove(inventory_name)
        logger.info(f"Inventory {inventory_name} deleted successfully.")
    else:
        logger.warning(f"Inventory {inventory_name} was not present.")

def get_instance_type(node):
    instance_pools = oci.pagination.list_call_get_all_results(compute_management_client.list_cluster_networks,node.compartment,display_name=node.cluster_name).data
    if len(instance_pools):
        for instance_pool in instance_pools:
            ipa_ocid=instance_pool.instance_pools[0].id
            instance_summaries = oci.pagination.list_call_get_all_results(compute_management_client.list_instance_pool_instances,node.compartment,ipa_ocid).data
            for instance_summary in instance_summaries:
                if instance_summary.id == node.ocid:
                    cluster_type="CN"
                    cluster_ocid=instance_pool.id
                    ipa_ocid=ipa_ocid
                    return cluster_type,cluster_ocid,ipa_ocid

    instance_pools = oci.pagination.list_call_get_all_results(compute_management_client.list_instance_pools,node.compartment,display_name=node.cluster_name).data
    if len(instance_pools):
        for instance_pool in instance_pools:
            instance_summaries = oci.pagination.list_call_get_all_results(compute_management_client.list_instance_pool_instances,node.compartment,instance_pool.id).data
            for instance_summary in instance_summaries:
                if instance_summary.id == node.ocid:
                    cluster_type="IPA"
                    cluster_ocid=instance_pool.id
                    ipa_ocid=instance_pool.id
                    return cluster_type,cluster_ocid,ipa_ocid
    try:
        instance_pools = compute_client.list_compute_clusters(node.compartment,display_name=node.cluster_name).data.items
    except:
        logger.warning(f"Compute clusters are not enabled in this region")
        instance_pools = []
    if len(instance_pools):
        for instance_pool in instance_pools:
            instance_summaries = compute_client.list_instances(node.compartment,compute_cluster_id=instance_pool.id).data
            for instance_summary in instance_summaries:
                if instance_summary.id == node.ocid:
                    cluster_type="CC"
                    cluster_ocid=instance_pool.id
                    ipa_ocid=instance_pool.id
                    return cluster_type,cluster_ocid,ipa_ocid
    instance_summaries = oci.pagination.list_call_get_all_results(compute_client.list_instances,compartment_id=node.compartment).data
    for instance_summary in instance_summaries:
        if instance_summary.id == node.ocid:
            cluster_type="SA"
            cluster_ocid=None
            ipa_ocid=None
            return cluster_type,cluster_ocid,ipa_ocid
    logger.warning(f"Node was not found, maybe it is missing tags?")
    return "SA",None,None

def create_cluster(config, count, cluster_name, controller_hostname, names):
    generate_inventory(config,cluster_name)
    if not config.stand_alone:
        instance_config_data=generate_instance_config(config, controller_hostname, cluster_name)
        instance_config_ocid=instance_config_data.id
        
        if config.rdma_enabled:
            ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=config.private_subnet_id)
            ip_placement_details=oci.core.models.ClusterNetworkPlacementConfigurationDetails(availability_domain=config.ad,primary_vnic_subnets=ip_placement_subnet_details)
            instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails(display_name=cluster_name,instance_configuration_id=instance_config_ocid,size=count)
            cn_details=oci.core.models.CreateClusterNetworkDetails(compartment_id=config.targetCompartment,display_name=cluster_name,instance_pools=[instance_pools_details],placement_configuration=ip_placement_details)
            cn = compute_management_client_composite_operations.create_cluster_network_and_wait_for_state(create_cluster_network_details=cn_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})
        else:
            ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=config.private_subnet_id)
            ip_placement_details=oci.core.models.CreateInstancePoolPlacementConfigurationDetails(availability_domain=config.ad,primary_vnic_subnets=ip_placement_subnet_details)
            instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails()
            ip_details=oci.core.models.CreateInstancePoolDetails(compartment_id=config.targetCompartment,display_name=cluster_name,placement_configurations=[ip_placement_details],instance_configuration_id=instance_config_ocid,size=count)
            cn = compute_management_client_composite_operations.create_instance_pool_and_wait_for_state(create_instance_pool_details=ip_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})
        
    else:
        if config.rdma_enabled:
            cc_details=oci.core.models.CreateComputeClusterDetails(compartment_id=config.targetCompartment,availability_domain=config.ad,display_name=cluster_name)
            cn = compute_client.create_compute_cluster(create_compute_cluster_details=cc_details).data
            cn_id=cn.id
        else:
            cn_id=None
        for i in range(count):
            launch_instance_details = getLaunchInstanceDetailsFromInstanceType(config, controller_hostname, cn_id, cluster_name, hostname=names[i])
            compute_client_composite_operations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])

def delete_cluster(cluster_name,nodes_list):
    cluster_type,cluster_ocid,ipa_ocid = get_instance_type(nodes_list[0])
    if cluster_type == "CN":
        compute_management_client.terminate_cluster_network(cluster_ocid)
    elif cluster_type == "IPA":
        compute_management_client.terminate_instance_pool(cluster_ocid)
    elif cluster_type == "CC" or cluster_type == "SA":
        for instance in nodes_list:
            compute_client_composite_operations.terminate_instance_and_wait_for_state(instance.ocid,wait_for_states=["TERMINATING","TERMINATED"])
        instance_running=True
        while instance_running:
            instance_running=False
            for instance in nodes_list:
                if compute_client.get_instance(instance.ocid).data.lifecycle_state != "TERMINATED":
                    instance_running=True
                    time.sleep(30)
        if cluster_type == "CC":
            compute_client.delete_compute_cluster(cluster_ocid)
    remove_inventory(cluster_name)
