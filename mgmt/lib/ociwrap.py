import base64
import os
import random
import re
import string
import sys
import time
import json
import ipaddress

from functools import cached_property
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import oci

from ClusterShell.NodeSet import NodeSet

from lib.database import (
    db_create_node,
    get_controller_node,
    get_nodes_by_id,
    db_update_node,
    get_nodes_by_cluster,
    get_nodes_by_memory_cluster,
    get_all_configs,
)
from lib.logger import logger


version = sys.version_info
if version >= (3, 12):
    UTC = timezone.utc

inventory_path="/config/playbooks/inventory"


class OCIClients:
    """
    Hold onto a cached set of OCI Clients so they can be instantiated on
    demand.
    """

    @cached_property
    def signer(self):
        return oci.auth.signers.InstancePrincipalsSecurityTokenSigner()

    @cached_property
    def compute_client(self):
        return oci.core.ComputeClient(config={}, signer=self.signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)

    @cached_property
    def compute_client_composite_operations(self):
        return oci.core.ComputeClientCompositeOperations(self.compute_client)

    @cached_property
    def compute_management_client(self):
        return oci.core.ComputeManagementClient(config={}, signer=self.signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)

    @cached_property
    def compute_management_client_composite_operations(self):
        return oci.core.ComputeManagementClientCompositeOperations(self.compute_management_client)

    @cached_property
    def virtual_network_client(self):
        return oci.core.VirtualNetworkClient(config={}, signer=self.signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)

    @cached_property
    def dns_client(self):
        return oci.dns.DnsClient(config={}, signer=self.signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)

    @cached_property
    def identity_client(self):
        return oci.identity.IdentityClient(config={}, signer=self.signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)

    @cached_property
    def identity_client_composite_operations(self):
        return oci.identity.IdentityClientCompositeOperations(self.identity_client)

    @cached_property
    def queue_admin_client(self):
        return oci.queue.QueueAdminClient(config={}, signer=self.signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)

    @cached_property
    def functions_management_client(self):
        return oci.functions.FunctionsManagementClient(config={}, signer=self.signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)


CLIENTS = OCIClients()

def invoke_node_event_function(function_id, node, event_type):
    function = CLIENTS.functions_management_client.get_function(function_id).data
    invoke_client = oci.functions.FunctionsInvokeClient(
        config={},
        signer=CLIENTS.signer,
        service_endpoint=function.invoke_endpoint,
        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY,
    )
    payload = {
        "data": {
            "resourceId": node.ocid,
            "compartmentId": node.compartment_id,
        },
        "eventType": event_type,
    }
    logger.info("Invoking function for %s with event %s (%s)", node.hostname, event_type, node.ocid)
    return invoke_client.invoke_function(
        function_id=function_id,
        invoke_function_body=json.dumps(payload).encode("utf-8"),
        fn_invoke_type="sync",
    ).data

def _get_instance_private_ip(instance):
    vnic_attachments = oci.pagination.list_call_get_all_results(
        CLIENTS.compute_client.list_vnic_attachments,
        compartment_id=instance.compartment_id,
        instance_id=instance.id,
    ).data
    if not vnic_attachments:
        return None

    primary_attachment = next(
        (attachment for attachment in vnic_attachments if getattr(attachment, "is_primary", False)),
        vnic_attachments[0],
    )
    vnic = CLIENTS.virtual_network_client.get_vnic(primary_attachment.vnic_id).data
    return vnic.private_ip

def list_tagged_cluster_nodes(compartment_id, cluster_name, controller_name, include_private_ip=False):
    instances = oci.pagination.list_call_get_all_results(
        CLIENTS.compute_client.list_instances,
        compartment_id=compartment_id,
        sort_by="TIMECREATED",
    ).data

    nodes = []
    for instance in instances:
        if instance.lifecycle_state == "TERMINATED":
            continue

        tags = instance.freeform_tags or {}
        if tags.get("cluster_name") != cluster_name:
            continue
        if tags.get("controller_name") != controller_name:
            continue

        private_ip = _get_instance_private_ip(instance) if include_private_ip else None
        nodes.append(SimpleNamespace(
            ocid=instance.id,
            compartment_id=instance.compartment_id,
            hostname=instance.display_name,
            ip_address=private_ip,
            cluster_name=tags.get("cluster_name"),
            controller_name=tags.get("controller_name"),
            lifecycle_state=instance.lifecycle_state,
            freeform_tags=tags,
        ))

    return nodes

def list_controller_tagged_nodes(include_private_ip=False):
    controller = get_controller_node()
    if not controller:
        raise ValueError("Controller node was not found in the mgmt DB.")

    return list_tagged_cluster_nodes(
        controller.compartment_id,
        controller.cluster_name,
        controller.controller_name,
        include_private_ip=include_private_ip,
    )


def list_instance_maintenance_events(compartment_id):
    """List every instance maintenance event in a compartment."""
    try:
        return oci.pagination.list_call_get_all_results(
            CLIENTS.compute_client.list_instance_maintenance_events,
            compartment_id=compartment_id,
        ).data
    except Exception as exc:
        logger.error(
            "Failed to list OCI instance maintenance events in compartment %s: %s",
            compartment_id,
            exc,
        )
        return []


def get_instance_maintenance_event(event_id):
    """Get a single instance maintenance event with detailed fault metadata."""
    try:
        return CLIENTS.compute_client.get_instance_maintenance_event(event_id).data
    except Exception as exc:
        logger.warning(
            "Failed to get details for OCI maintenance event %s: %s",
            event_id,
            exc,
        )
        return None


def reschedule_instance_maintenance_event(event_id, delay_minutes=5):
    """Move a maintenance event's start window to now plus the given delay."""
    time_window_start = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    details = oci.core.models.UpdateInstanceMaintenanceEventDetails(
        time_window_start=time_window_start,
    )
    try:
        response = CLIENTS.compute_client.update_instance_maintenance_event(
            instance_maintenance_event_id=event_id,
            update_instance_maintenance_event_details=details,
        )
    except Exception as exc:
        logger.error(
            "Failed to update OCI maintenance event %s: %s",
            event_id,
            exc,
        )
        return None, None
    return response.data, time_window_start


def _get_controller_config_fss_hostname():
    controller = get_controller_node()
    if not controller or not controller.ocid:
        logger.warning("Controller node was not found in the mgmt DB.")
        return None

    controller_instance = CLIENTS.compute_client.get_instance(controller.ocid).data
    config_fss_hostname = (controller_instance.freeform_tags or {}).get("config_fss_hostname")
    if not config_fss_hostname:
        logger.warning("config_fss_hostname tag was not found on the controller.")
    return config_fss_hostname

def _add_config_fss_hostname_tag(tags):
    tags = dict(tags or {})
    config_fss_hostname = _get_controller_config_fss_hostname()
    if config_fss_hostname:
        tags["config_fss_hostname"] = config_fss_hostname
    return tags

def get_console_history(node):
    # Capture console history for the instance
    try:
        console_history_response = CLIENTS.compute_client_composite_operations.capture_console_history_and_wait_for_state(oci.core.models.CaptureConsoleHistoryDetails(
            instance_id=node.ocid), wait_for_states=["SUCCEEDED", "FAILED"])
        console_history_id = console_history_response.data.id
        console_history_data = CLIENTS.compute_client.get_console_history_content(console_history_id).data
        return console_history_data
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error capturing console history for instance {node.ocid}: {e}")
        return None

def list_custom_images(compartment_ocid):
    custom_images = []
    if not compartment_ocid:
        logger.error("Cannot retrieve custom images without a compartment OCID")
        return custom_images
    try:
        response = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_images,compartment_id=compartment_ocid)
        if response.data:
            for image in response.data:
                custom_images.append(image)
        else:
            logger.info(f"No custom images found in compartment {compartment_ocid}.")
    except oci.exceptions.ServiceError as e:
         logger.error(f"Error retrieving custom images from compartment {compartment_ocid}: {e}")
    return custom_images

def pick_custom_images(compartment_ocid):
    if not compartment_ocid:
        raise ValueError("Cannot select a custom image because no compartment OCID was found")
    custom_images = list_custom_images(compartment_ocid)
    if not custom_images:
        raise ValueError(f"No custom images found in compartment {compartment_ocid}")
    for i, img in enumerate(custom_images):
        print(f"{i+1}. {img.display_name} ({img.id})")
    # Ask user to choose a custom image
    choice = int(input("Enter the number of the custom image to use: ")) - 1
    image_ocid = custom_images[choice].id
    return image_ocid

def add_shape_to_image(image_ocid_name, compartment_ocid, shape):
    try:
        image = CLIENTS.compute_client.get_image(image_ocid_name).data
        image_ocid=image_ocid_name
        image_name=image.display_name
    except:
        logger.debug("Image with OCID is not found, trying with image name")
        images=CLIENTS.compute_client.list_images(compartment_id=compartment_ocid,display_name=image_ocid_name)
        if images.data:
            image=images.data[0]
            image_ocid=image.id
            image_name=image.display_name
        else:
            logger.error(f"Image {image_ocid_name} not found in compartment {compartment_ocid}")
            return
    shape_compatibility_entries=CLIENTS.compute_client.list_image_shape_compatibility_entries(image_ocid).data


    for shape_compatibility_entry in shape_compatibility_entries:
        if shape == shape_compatibility_entry.shape:
            logger.info(f"Shape {shape} already exists for image {image_name}")
            return

    CLIENTS.compute_client.add_image_shape_compatibility_entry(image_id=image_ocid,shape_name=shape)
    logger.info(f"Shape {shape} added to image {image_name}")

def import_custom_image(url,compartment_ocid):
    name = url.split("/")[-1]
    try:
        image_source_details = oci.core.models.ImageSourceViaObjectStorageUriDetails(source_uri=url)
        image_details = oci.core.models.CreateImageDetails(image_source_details=image_source_details,display_name=name,compartment_id=compartment_ocid)
        CLIENTS.compute_client.create_image(image_details)

    except oci.exceptions.ServiceError as e:
        logger.error(f"Error creating custom image: {e}")

def run_boot_volume_swap(node,image_ocid,size):
    update_instance_source_details = oci.core.models.UpdateInstanceSourceViaImageDetails()
    update_instance_source_details.image_id = image_ocid
    update_instance_source_details.is_preserve_boot_volume_enabled = False
    update_instance_source_details.is_force_stop_enabled = True
    if size is not None:
        update_instance_source_details.boot_volume_size_in_gbs = size
    update_instance_details = oci.core.models.UpdateInstanceDetails()
    update_instance_details.source_details = update_instance_source_details

    try:
        CLIENTS.compute_client_composite_operations.update_instance_and_wait_for_state(
            node.ocid,
            update_instance_details,
            wait_for_states=["STOPPING","STOPPED","STARTING","RUNNING"]
        )
    except oci.exceptions.ServiceError as e:
        if e.code == "InvalidParameter":
            add_shape_to_image(image_ocid, node.compartment_id, node.shape)
            CLIENTS.compute_client_composite_operations.update_instance_and_wait_for_state(
                node.ocid,
                update_instance_details,
                wait_for_states=["STOPPING","STOPPED","STARTING","RUNNING"]
            )
        else:
            logger.error(f"Error: {e}")
    time.sleep(1)

def log_terminate_timeout(node, timeout_error):
    try:
        state = CLIENTS.compute_client.get_instance(node.ocid).data.lifecycle_state
    except oci.exceptions.ServiceError as e:
        if e.status == 404:
            logger.info(f"Node {node.hostname} is already terminated: {e.code}")
        else:
            logger.error(f"Timed out waiting for {node.hostname} to terminate and failed to read current OCI state: {e}")
        return

    if state == "TERMINATED":
        logger.info(f"Node {node.hostname} is terminated; OCI waiter timed out before observing completion")
    else:
        logger.error(f"Timed out waiting for {node.hostname} to terminate: {timeout_error}; current OCI state is {state}")

def run_terminate(node):
    cluster_type,cluster_ocid,instance_pool_ocid = get_instance_type(node)
    try:
        if cluster_type == "SA" or cluster_type == "CC":
            logger.info(f"Terminating node with details {node.hostname}, {node.oci_name}, {node.ip_address}, {node.serial}")
            if hasattr(CLIENTS.compute_client_composite_operations, "terminate_instance_and_wait_for_work_request"):
                CLIENTS.compute_client_composite_operations.terminate_instance_and_wait_for_work_request(node.ocid,work_request_states=["STATUS_SUCCEEDED"],waiter_kwargs={'max_wait_seconds': 600})
            else:
                CLIENTS.compute_client_composite_operations.terminate_instance_and_wait_for_state(node.ocid,wait_for_states=["TERMINATING", "TERMINATED"],waiter_kwargs={'max_wait_seconds': 600})
        elif cluster_type == "IPA" or cluster_type == "CN":
            logger.info(f"Terminating node with details {node.hostname}, {node.oci_name}, {node.ip_address}, {node.serial}")
            instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=node.ocid,is_auto_terminate=True,is_decrement_size=True)
            CLIENTS.compute_management_client_composite_operations.detach_instance_pool_instance_and_wait_for_work_request(instance_pool_ocid,instance_details,waiter_kwargs={'max_wait_seconds': 600})
    except (
        oci.exceptions.CompositeOperationError,
        oci.exceptions.MaximumWaitTimeExceeded,
        oci.exceptions.ServiceError,
    ) as e:
        error = getattr(e, "cause", None) or e
        if isinstance(error, oci.exceptions.MaximumWaitTimeExceeded):
            log_terminate_timeout(node, error)
        elif isinstance(error, oci.exceptions.ServiceError) and error.status == 404:
            logger.info(f"Node {node.hostname} is already terminated: {error.code}")
        else:
            logger.error(f"Error terminating {node.hostname}: {error}")

def run_terminate_no_wait(node):
    cluster_type,cluster_ocid,instance_pool_ocid = get_instance_type(node)
    try:
        if cluster_type == "SA" or cluster_type == "CC":
            logger.info(f"Submitting termination request for node {node.hostname}, {node.oci_name}, {node.ip_address}, {node.serial}")
            CLIENTS.compute_client.terminate_instance(node.ocid)
        elif cluster_type == "IPA" or cluster_type == "CN":
            logger.info(f"Submitting detach request for node {node.hostname}, {node.oci_name}, {node.ip_address}, {node.serial}")
            instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=node.ocid,is_auto_terminate=True,is_decrement_size=True)
            CLIENTS.compute_management_client.detach_instance_pool_instance(instance_pool_ocid,instance_details)
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error: {e}")

def run_reboot(node,soft):
    try:
        if soft:
            logger.info("Soft Rebooting: "+str(node.hostname)+" with oci name "+str(node.oci_name)+" with IP "+str(node.ip_address)+" and OCID:"+str(node.ocid))
            CLIENTS.compute_client.instance_action(instance_id=node.ocid,action="SOFTRESET")
        else:
            logger.info("Force Rebooting: "+str(node.hostname)+" with oci name "+str(node.oci_name)+" with IP "+str(node.ip_address)+" and OCID:"+str(node.ocid))
            CLIENTS.compute_client.instance_action(instance_id=node.ocid,action="RESET")
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error: {e}")

def run_stop(node,soft):
    try:
        if soft:
            logger.info("Soft Stopping: "+str(node.hostname)+" with oci name "+str(node.oci_name)+" with IP "+str(node.ip_address)+" and OCID:"+str(node.ocid))
            CLIENTS.compute_client.instance_action(instance_id=node.ocid,action="SOFTSTOP")
        else:
            logger.info("Stopping: "+str(node.hostname)+" with oci name "+str(node.oci_name)+" with IP "+str(node.ip_address)+" and OCID:"+str(node.ocid))
            CLIENTS.compute_client.instance_action(instance_id=node.ocid,action="STOP")
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error: {e}")

def run_tag(node):
    instance = CLIENTS.compute_client.get_instance(instance_id=node.ocid).data
    tags = instance.defined_tags
    tags.update({'ComputeInstanceHostActions': { 'CustomerReportedHostStatus': 'unhealthy' }})
    update_instance_details = oci.core.models.UpdateInstanceDetails(defined_tags=tags)
    logger.info("Updating tags on instance: "+node.hostname+" with OCID:"+node.ocid)
    try:
        CLIENTS.compute_client_composite_operations.update_instance_and_wait_for_state(node.ocid, update_instance_details,wait_for_states=["RUNNING"])
    except oci.exceptions.ServiceError as e:
        logger.error("The tag does not exists or the controller doesn't have acces to the tag")
        logger.error("Make sure the Tag namespace ComputeInstanceHostActions exists with the defined tag: CustomerReportedHostStatus")

def run_enable_instance_rdma_plugins(node):
    instance_rdma_plugins = ("Compute HPC RDMA Authentication", "Compute HPC RDMA Auto-Configuration")
    logger.info("Enabling RDMA plugins on instance: " + node.hostname + " with OCID:"+node.ocid)
    try:
        instance = CLIENTS.compute_client.get_instance(instance_id=node.ocid).data
        plugins_by_name = {}
        agent_config = instance.agent_config
        if agent_config and agent_config.plugins_config:
            for plugin in agent_config.plugins_config:
                plugins_by_name[plugin.name] = plugin.desired_state
        for name in instance_rdma_plugins:
            plugins_by_name[name] = "ENABLED"
        plugins_config = [
            oci.core.models.InstanceAgentPluginConfigDetails(desired_state=state, name=name)
            for name, state in plugins_by_name.items()
        ]
        new_agent_config = oci.core.models.UpdateInstanceAgentConfigDetails(plugins_config=plugins_config)
        update_instance_details = oci.core.models.UpdateInstanceDetails(agent_config=new_agent_config)
        CLIENTS.compute_client.update_instance(node.ocid, update_instance_details)
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error enabling RDMA plugins on {node.hostname}: {e}")

def run_add(nodes, count, names, cluster, compartment_ocid, memory_cluster_ocid=None):
    if memory_cluster_ocid:
        memory_cluster_data = CLIENTS.compute_client.get_compute_gpu_memory_cluster(
            memory_cluster_ocid
        ).data
        cluster_type = "MC"
        cluster_ocid = memory_cluster_data.id
        cluster_name = memory_cluster_data.display_name
    elif not nodes:
        if cluster is None:
            logger.error("The resize script cannot work for a cluster if there are no nodes in the cluster")
            sys.exit(1)
        else:
            logger.debug("No nodes found, checking if there is a Cluster Network with that name")
            clusters=CLIENTS.compute_management_client.list_cluster_networks(compartment_id=compartment_ocid,display_name=cluster,lifecycle_state="RUNNING").data
            if not clusters:
                instance_pools=CLIENTS.compute_management_client.list_instance_pools(compartment_id=compartment_ocid,display_name=cluster,lifecycle_state="RUNNING").data
                if not instance_pools:
                    logger.error("No cluster found with name: {}".format(cluster))
                    sys.exit(1)
                elif len(instance_pools) > 1:
                    logger.error("Multiple clusters found with name: {}".format(cluster))
                    sys.exit(1)
                else:
                    cluster_type="IPA"
                    cluster_ocid=instance_pools[0].id
                    instance_pool_ocid=instance_pools[0].id
                    cluster_name=instance_pools[0].display_name
            elif len(clusters) > 1:
                logger.error("Multiple clusters found with name: {}".format(cluster))
                sys.exit(1)
            else:
                cluster_type="CN"
                cluster_ocid=clusters[0].id
                instance_pool_ocid=clusters[0].instance_pools[0].id
                cluster_name=clusters[0].display_name
    if nodes:
        first_node=None
        if len(nodes):
            for node in nodes:
                if node.cluster_name and node.controller_name:
                    first_node=node
                    break
        if "GPU.GB" in first_node.shape:
            memory_cluster=CLIENTS.compute_client.get_compute_gpu_memory_cluster(first_node.memory_cluster_id).data
            mc_id=memory_cluster.id
            instance_summaries = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_compute_gpu_memory_cluster_instances, mc_id).data
            for instance_summary in instance_summaries:
                if instance_summary.id == first_node.ocid:
                    memory_cluster_data=CLIENTS.compute_client.get_compute_gpu_memory_cluster(mc_id).data
                    cc_id=memory_cluster_data.compute_cluster_id
                    instance_config_id=memory_cluster_data.instance_configuration_id
                    cluster_type="MC"
                    cluster_ocid=mc_id
                    cluster_name=memory_cluster_data.display_name
        else:
            logger.debug(f"The first node name is {first_node.hostname}")
            cluster_type,cluster_ocid,instance_pool_ocid = get_instance_type(first_node)
            cluster_name=first_node.cluster_name
            logger.debug(f"The detected type is {cluster_type} and the cluster name is {cluster_name}")
    current_size=get_instance_count(cluster_type,cluster_ocid,compartment_ocid,cluster_name)
    logger.debug(f"The detected type is {cluster_type} with a size of {current_size}")
    target_size = current_size + count
    logger.debug(f"The target size is {target_size}")

    if cluster_type == "CC" or cluster_type == "SA":
        logger.debug("The detected type is Compute cluster or Stand Alone node")
        first_instance=CLIENTS.compute_client.get_instance(first_node.ocid).data
        logger.info(f"Launching {count} in the Cluster")
        for i in range(count):
            if cluster_type == "CC":
                if names:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,cluster_ocid,first_node.compartment_id,first_node.cluster_name,hostname=names[i])
                else:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,cluster_ocid,first_node.compartment_id,first_node.cluster_name)
            else:
                if names:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,None,first_node.compartment_id,first_node.cluster_name,hostname=names[i])
                else:
                    launch_instance_details=getLaunchInstanceDetailsFromInstance(first_instance,None,first_node.compartment_id,first_node.cluster_name)
            logger.info(f"Launching {count} in the Cluster for a total size of {target_size}")
            CLIENTS.compute_client_composite_operations.launch_instance_and_wait_for_state(launch_instance_details)
    elif cluster_type == "MC":
        logger.debug("The detected type is Compute GPU Memory Cluster")
        update_compute_gpu_memory_cluster_details = oci.core.models.UpdateComputeGpuMemoryClusterDetails(size=target_size)
        logger.info(f"Launching {count} in the Cluster for a total size of {target_size}")
        CLIENTS.compute_client.update_compute_gpu_memory_cluster(cluster_ocid,update_compute_gpu_memory_cluster_details)
    else:
        logger.debug("The detected type is Instance Pool/Cluster Network")
        if names:
            logger.info("Host names are ignored for Instance Pools and Cluster Networks")
        update_size = oci.core.models.UpdateInstancePoolDetails(size=target_size)
        logger.info(f"Launching {count} in the Cluster for a total size of {target_size}")
        CLIENTS.compute_management_client_composite_operations.update_instance_pool_and_wait_for_state(instance_pool_ocid,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
    newsize=get_instance_count(cluster_type,cluster_ocid,compartment_ocid,cluster_name)
    if cluster_type != "MC":
        logger.info(f"Total number of nodes in the cluster is now {newsize} with a requested size of {target_size}")
        if newsize == current_size:
            logger.error("No node was added, please check the work requests of the Cluster Network and Instance Pool to see why")
            sys.exit(1)


def _region_from_ocid(ocid):
    parts = ocid.split(".")
    if len(parts) > 3 and parts[3]:
        return parts[3]
    return "<region>"


def _compute_gpu_memory_cluster_request_body(
    availability_domain,
    compartment_id,
    cc_id,
    instance_config_ocid,
    count,
    fabric_id,
    gpu_memory_cluster_name,
    targetsize=0,
):
    request_body = {
        "availabilityDomain": availability_domain,
        "compartmentId": compartment_id,
        "computeClusterId": cc_id,
        "instanceConfigurationId": instance_config_ocid,
        "size": int(count),
        "gpuMemoryFabricId": fabric_id,
        "displayName": gpu_memory_cluster_name,
    }
    if int(targetsize) != 0:
        request_body["gpuMemoryClusterScaleConfig"] = {
            "isDownsizeEnabled": True,
            "isUpsizeEnabled": True,
            "targetSize": int(targetsize),
        }
    return request_body


def _print_compute_gpu_memory_cluster_raw_request(request_body, fabric_id):
    region = _region_from_ocid(fabric_id)
    print("Resolved create_compute_gpu_memory_cluster request body:")
    print(json.dumps(request_body, indent=2))
    print()
    print("Equivalent OCI raw-request command:")
    print("cat > /tmp/create-gpu-memory-cluster.json <<'JSON'")
    print(json.dumps(request_body, indent=2))
    print("JSON")
    print()
    print("oci raw-request \\")
    print("  --http-method POST \\")
    print(f'  --target-uri "https://iaas.{region}.oraclecloud.com/20160918/computeGpuMemoryClusters" \\')
    print("  --request-body file:///tmp/create-gpu-memory-cluster.json")


def run_add_memory_fabric(nodes, controller, count, fabric_id , gpu_memory_cluster_name, instancetype=None, compute_cluster_id=None, compute_cluster_name=None, targetsize=0, dump_command=False):
    if fabric_id is None:
        logger.error("For BM.GPU.GB200.4, BM.GPU.GB200-v2.4, BM.GPU.GB200-v3.4, or BM.GPU.GB300.4, the memory fabric needs to be specified, Exiting")
        sys.exit(1)
    if len(nodes) == 0 and (instancetype is None or compute_cluster_name is None):
        logger.error("No nodes found in the cluster and no instance type or compute cluster ID has been specified")
        sys.exit(1)

    first_node=None
    if len(nodes):
        for node in nodes:
            if node.cluster_name and node.controller_name and getattr(node, 'memory_cluster_id', None):
                first_node=node
                break

    if first_node is None:
        compartment_id=controller.compartment_id
        if instancetype is None:
            logger.error("No nodes found in the cluster and no instance type has been specified")
            sys.exit(1)
        instance_config_data=generate_instance_config(instancetype, controller.hostname, compute_cluster_name, memory_cluster_name=gpu_memory_cluster_name)
        instance_config_ocid=instance_config_data.id

        if compute_cluster_id is None:
            cc_list = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_compute_clusters, compartment_id=compartment_id, display_name=compute_cluster_name).data
            running_cc_list=[cc for cc in cc_list if cc.lifecycle_state == "ACTIVE" and cc.display_name == compute_cluster_name] #The filter on list_compute_clusters is broken
            if len(running_cc_list) > 1:
                logger.error("We found multiple running compute clusters with that cluster name, specify Compute Cluster OCID")
                sys.exit(1)
            elif len(running_cc_list) == 0:
                logger.error("No running compute clusters found with that cluster name")
                sys.exit(1)
            else:
                cc_id=running_cc_list[0].id
                availability_domain=running_cc_list[0].availability_domain
        else:
            cc_id = compute_cluster_id
            availability_domain=CLIENTS.compute_client.get_compute_cluster(cc_id).data.availability_domain
    else:
        availability_domain = first_node.availability_domain
        compartment_id = controller.compartment_id
        all_memory_clusters = _response_items(oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_compute_gpu_memory_clusters, compartment_id=compartment_id, display_name=first_node.memory_cluster_id).data)
        memory_clusters = [entry for entry in all_memory_clusters if entry.lifecycle_state == "ACTIVE"]
        if len(memory_clusters) == 0 :
            try:
                memory_clusters = [CLIENTS.compute_client.get_compute_gpu_memory_cluster(first_node.memory_cluster_id).data]
            except oci.exceptions.ServiceError as e:
                memory_clusters = []
        if len(memory_clusters) == 0:
            logger.error("No memory clusters found with that name or OCID")
            sys.exit(1)
        else:
            for memory_cluster in memory_clusters:
                mc_id = memory_cluster.id
                memory_cluster_data = CLIENTS.compute_client.get_compute_gpu_memory_cluster(mc_id).data
                cc_id = memory_cluster_data.compute_cluster_id
                if compute_cluster_id is not None:
                    if cc_id != compute_cluster_id:
                        logger.error("The compute cluster ID you specified does not match the compute cluster ID of the nodes in the current cluster")
                        sys.exit(1)
                instance_config_ocid=memory_cluster_data.instance_configuration_id
                break
    request_body = _compute_gpu_memory_cluster_request_body(
        availability_domain,
        compartment_id,
        cc_id,
        instance_config_ocid,
        count,
        fabric_id,
        gpu_memory_cluster_name,
        targetsize=targetsize,
    )
    if dump_command:
        _print_compute_gpu_memory_cluster_raw_request(request_body, fabric_id)
        return

    if targetsize != 0:
        clusterScaleConfig=oci.core.models.CreateComputeGpuMemoryClusterScaleConfig(is_downsize_enabled=True, is_upsize_enabled=True, target_size=int(targetsize))
        compute_gpu_memory_cluster_details=oci.core.models.CreateComputeGpuMemoryClusterDetails(
            availability_domain=availability_domain,
            compartment_id=compartment_id,
            compute_cluster_id=cc_id,
            instance_configuration_id=instance_config_ocid,
            size=int(count),
            gpu_memory_fabric_id=fabric_id,
            display_name=gpu_memory_cluster_name,
            gpu_memory_cluster_scale_config=clusterScaleConfig)
        try:
            CLIENTS.compute_client.create_compute_gpu_memory_cluster(compute_gpu_memory_cluster_details)
        except:
            logger.error("Failed to create compute GPU memory cluster, you specified a non-0 target size. Are you whitelisted for it? ")
            sys.exit(1)
    else:
        compute_gpu_memory_cluster_details=oci.core.models.CreateComputeGpuMemoryClusterDetails(
            availability_domain=availability_domain,
            compartment_id=compartment_id,
            compute_cluster_id=cc_id,
            instance_configuration_id=instance_config_ocid,
            size=int(count),
            gpu_memory_fabric_id=fabric_id,
            display_name=gpu_memory_cluster_name)
        CLIENTS.compute_client.create_compute_gpu_memory_cluster(compute_gpu_memory_cluster_details)

def getLaunchInstanceDetailsFromInstance(first_instance,cluster_ocid,compartment_ocid,cluster_name,hostname=None):

    agent_config=first_instance.agent_config
    agent_config.__class__ = oci.core.models.LaunchInstanceAgentConfigDetails

    for potential_vnic_attachment in oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_vnic_attachments,compartment_id=compartment_ocid,instance_id=first_instance.id).data:
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

    freeform_tags=_add_config_fss_hostname_tag(first_instance.freeform_tags)
    if hostname is None:
        new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+cluster_name
    else:
        new_display_name=hostname
        if "hostname_convention" in freeform_tags.keys():
            freeform_tags.pop("hostname_convention")

    legacy_imds_off = oci.core.models.InstanceOptions(are_legacy_imds_endpoints_disabled = True)

    if first_instance.shape.startswith("BM"):
        launch_instance_details=oci.core.models.LaunchInstanceDetails(
                agent_config=agent_config,
                availability_domain=first_instance.availability_domain,
                compartment_id=compartment_ocid,
                compute_cluster_id=cluster_ocid,
                shape=first_instance.shape,
                source_details=first_instance.source_details,
                metadata=first_instance.metadata,
                display_name=new_display_name,
                freeform_tags=freeform_tags,
                create_vnic_details=create_vnic_details,
                instance_options = legacy_imds_off,
                )
    else:
        launch_instance_details=oci.core.models.LaunchInstanceDetails(
                agent_config=agent_config,
                availability_domain=first_instance.availability_domain,
                compartment_id=compartment_ocid,
                compute_cluster_id=cluster_ocid,
                shape=first_instance.shape,
                shape_config=launchInstanceShapeConfigDetails,
                source_details=first_instance.source_details,
                metadata=first_instance.metadata,
                display_name=new_display_name,
                freeform_tags=freeform_tags,
                create_vnic_details=create_vnic_details,
                instance_options = legacy_imds_off,
                )
    return launch_instance_details

def get_instance_count(cluster_type,cluster_ocid,compartment_ocid,cluster_name):
    if cluster_type == "SA" or cluster_type == "CC":
        matching_instances=[]
        if cluster_type == "CC":
            instances = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_instances,compartment_id=compartment_ocid,compute_cluster_id=cluster_ocid,sort_by="TIMECREATED").data
        else:
            instances = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_instances,compartment_id=compartment_ocid,sort_by="TIMECREATED").data
        for instance in instances:
            if instance.lifecycle_state == "TERMINATED":
                continue
            elif len(instance.freeform_tags) == 0:
                continue
            elif "controller" in instance.freeform_tags.keys() or "login" in instance.freeform_tags.keys() or "monitoring" in instance.freeform_tags.keys() or "slurm_backup" in instance.freeform_tags.keys():
                continue
            elif "cluster_name" in instance.freeform_tags.keys():
                if instance.freeform_tags["cluster_name"]==cluster_name:
                    matching_instances.append(instance)
        return(len(matching_instances))
    elif cluster_type == "CN":
        instance_summaries = oci.pagination.list_call_get_all_results(CLIENTS.compute_management_client.list_cluster_network_instances,compartment_ocid,cluster_ocid,sort_by="TIMECREATED").data
        return(len(instance_summaries))
    elif cluster_type == "IPA":
        instance_summaries = oci.pagination.list_call_get_all_results(CLIENTS.compute_management_client.list_instance_pool_instances,compartment_ocid,cluster_ocid,sort_by="TIMECREATED").data
        return(len(instance_summaries))
    elif cluster_type == "MC":
        instance_summaries = CLIENTS.compute_client.list_compute_gpu_memory_cluster_instances(cluster_ocid).data.items
        return(len(instance_summaries))

def _get_node_compartment_id(node):
    compartment_id = getattr(node, "compartment_id", None)
    if compartment_id:
        return compartment_id

    instance_ocid = getattr(node, "ocid", None)
    if instance_ocid:
        try:
            compartment_id = CLIENTS.compute_client.get_instance(instance_ocid).data.compartment_id
            if compartment_id:
                logger.info(
                    "Resolved compartment %s from OCI instance %s",
                    compartment_id,
                    getattr(node, "hostname", None) or instance_ocid,
                )
                return compartment_id
        except oci.exceptions.ServiceError as e:
            logger.error(f"Error retrieving compartment for instance {instance_ocid}: {e}")

    controller = get_controller_node()
    if controller and getattr(controller, "compartment_id", None):
        logger.warning(
            "Node %s does not have a compartment_id; using controller compartment %s",
            getattr(node, "hostname", None) or instance_ocid,
            controller.compartment_id,
        )
        return controller.compartment_id

    logger.error(
        "Cannot determine compartment for node %s",
        getattr(node, "hostname", None) or instance_ocid,
    )
    sys.exit(1)

def get_instance_type(node):
    compartment_id = _get_node_compartment_id(node)
    try:
        instance_pools = oci.pagination.list_call_get_all_results(CLIENTS.compute_management_client.list_cluster_networks,compartment_id,display_name=node.cluster_name,lifecycle_state="RUNNING").data
        if len(instance_pools):
            logger.debug(f"Found Cluster Network with name {node.cluster_name}")
            for instance_pool in instance_pools:
                ipa_ocid=instance_pool.instance_pools[0].id
                instance_summaries = oci.pagination.list_call_get_all_results(CLIENTS.compute_management_client.list_instance_pool_instances,compartment_id,ipa_ocid).data
                for instance_summary in instance_summaries:
                    if instance_summary.id == node.ocid:
                        cluster_type="CN"
                        cluster_ocid=instance_pool.id
                        ipa_ocid=ipa_ocid
                        return cluster_type,cluster_ocid,ipa_ocid
    except oci.exceptions.ServiceError as e:
        logger.warning("CLuster Network are not enabled in this region")
        instance_pools = []
    instance_pools = oci.pagination.list_call_get_all_results(CLIENTS.compute_management_client.list_instance_pools,compartment_id,display_name=node.cluster_name).data
    if len(instance_pools):
        logger.debug(f"Found Instance Pool with name {node.cluster_name}")
        for instance_pool in instance_pools:
            instance_summaries = oci.pagination.list_call_get_all_results(CLIENTS.compute_management_client.list_instance_pool_instances,compartment_id,instance_pool.id).data
            for instance_summary in instance_summaries:
                logger.debug(f"instance_summary.id = {instance_summary.id}")
                if instance_summary.id == node.ocid:
                    logger.debug(f"Found Node in Instance Pool {node.ocid}")
                    cluster_type="IPA"
                    cluster_ocid=instance_pool.id
                    ipa_ocid=instance_pool.id
                    return cluster_type,cluster_ocid,ipa_ocid
    try:
        compute_clusters_list = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_compute_clusters, compartment_id, display_name=node.cluster_name).data
        compute_clusters = [entry for entry in compute_clusters_list if entry.lifecycle_state == "ACTIVE" and entry.display_name == node.cluster_name]
    except:
        logger.warning("Compute clusters are not enabled in this region")
        compute_clusters = []
    if len(compute_clusters):
        logger.debug(f"Found Compute Cluster with name {node.cluster_name}")
        for cc in compute_clusters:
            cc_instances = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_instances, compartment_id, compute_cluster_id=cc.id).data
            for instance_summary in cc_instances:
                if instance_summary.id == node.ocid:
                    cluster_type="CC"
                    cluster_ocid=cc.id
                    ipa_ocid=cc.id
                    return cluster_type, cluster_ocid, ipa_ocid
    instance_summaries = oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_instances, compartment_id=compartment_id).data
    for instance_summary in instance_summaries:
        if instance_summary.id == node.ocid:
            cluster_type="SA"
            cluster_ocid=None
            ipa_ocid=None
            return cluster_type, cluster_ocid, ipa_ocid
    logger.warning("Node was not found, maybe it is missing tags?")
    return "SA", None, None

def oci_scan_queue_and_update_db(controller_name):

    queue_ocid=get_queue_ocid()
    endpoint = CLIENTS.queue_admin_client.get_queue(queue_ocid).data.messages_endpoint
    queue_client = oci.queue.QueueClient(config={}, signer=CLIENTS.signer, service_endpoint=endpoint, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
    nodes_to_add=[]
    nodes_to_remove=[]
    while True:
        messages_response = queue_client.get_messages(queue_ocid,limit=20,channel_filter=controller_name)
        if len(messages_response.data.messages) == 0:
            break
        logger.debug(f"{len(messages_response.data.messages)} messages found in the queue")

        messages = messages_response.data.messages
        for message in messages:
            try:
                content=eval(message.content)
                logger.debug(str(content))
                if content['status'] == "starting":
                    logger.debug("Node is starting")
                    if "compartment" in content.keys():
                        content['compartment_id']=content['compartment']
                        del content["compartment"]
                    content['controller_status']="configuring"
                    content['started_time']=current_time_str
                    nodes_to_add.append(content)
                    db_create_node(content["ocid"], **content)
                    queue_client.delete_message(queue_ocid, message.receipt)
                elif content['status'] == "terminating":
                    logger.debug("Node is terminating")
                    logger.debug(NodeSet(content["ocid"]))
                    logger.debug(get_nodes_by_id(NodeSet(content["ocid"])))
                    existing_nodes=get_nodes_by_id(NodeSet(content["ocid"]))
                    if len(existing_nodes):
                        node = existing_nodes[0]
                        db_update_node(node,controller_status="terminating",terminated_time=current_time_str,compute_status="terminating")
                        logger.debug("Node: hostname=%s, controller_status=%s, terminated_time=%s", node.hostname, node.controller_status, node.terminated_time)
                    else:
                        logger.debug("Node not found in the DB")
                    queue_client.delete_message(queue_ocid, message.receipt)
                    logger.debug("Message is deleted")
            except Exception as e:
                logger.error(f"Error evaluating message {message.content}: {e}")

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

def get_host_api_dict(compartment, tenancy):
    try:
        compartment_host_api=oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_compute_hosts, compartment_id=compartment).data
    except:
        compartment_host_api=[]
    try:
        tenancy_host_api=oci.pagination.list_call_get_all_results(CLIENTS.compute_client.list_compute_hosts, compartment_id=tenancy).data
    except:
        tenancy_host_api=[]
    return compartment_host_api + tenancy_host_api

def get_marketplace_image(marketplace_listing, compartment_id):
    config_path = "/config/conf/marketplace.conf"
    try:
        # Read & parse config file
        with open(config_path, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        return None
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in {config_path}")
        return None

    # Determine listing_id by prefix
    prefix = (marketplace_listing or "")[:3]
    try:
        if prefix == "HPC":
            marketplace_listing_id = config["marketplace_listing_id_HPC"]
        elif prefix == "GPU":
            marketplace_listing_id = config["marketplace_listing_id_GPU"]
        else:
            logger.error(f"marketplace_listing '{marketplace_listing}' does not start with 'HPC' or 'GPU'.")
            return None
        marketplace_version_id = config["marketplace_version_id"][marketplace_listing]
    except KeyError as ke:
        logger.error(f"Missing expected key in config: {ke}")
        return None

    # Get app catalog listing agreement
    try:
        get_agreement_response = CLIENTS.compute_client.get_app_catalog_listing_agreements(
            listing_id=marketplace_listing_id,
            resource_version=marketplace_version_id
        )
        agreement = get_agreement_response.data
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error retrieving agreement for listing: {marketplace_listing_id} version: {marketplace_version_id} — {e.message}")
        return None

    # Create app catalog subscription (ignore if already exists)
    subscription_details = oci.core.models.CreateAppCatalogSubscriptionDetails(
        compartment_id=compartment_id,
        listing_id=agreement.listing_id,
        listing_resource_version=agreement.listing_resource_version,
        oracle_terms_of_use_link=agreement.oracle_terms_of_use_link,
        signature=agreement.signature,
        time_retrieved=agreement.time_retrieved
    )
    try:
        CLIENTS.compute_client.create_app_catalog_subscription(subscription_details)
    except oci.exceptions.ServiceError as e:
        if e.status != 409:  # 409 = already exists ("Conflict"), can safely ignore
            logger.error(f"Error creating app catalog subscription: {e.message}")
            return None

    # Get the image OCID
    try:
        get_app_catalog_listing_response = CLIENTS.compute_client.get_app_catalog_listing_resource_version(
            listing_id=marketplace_listing_id,
            resource_version=marketplace_version_id
        )
        return get_app_catalog_listing_response.data.listing_resource_id
    except oci.exceptions.ServiceError as e:
        logger.error(f"Error retrieving image OCID: {e.message}")
        return None

def getLaunchInstanceDetailsFromInstanceType(config, controller_hostname, cn_ocid, cluster_name, hostname=None):

    subnet_id=config.private_subnet_id
    image_id=config.image_id
    bv_size=config.boot_volume_size
    availability_domain=config.availability_domain
    target_compartment_id=config.target_compartment_id
    shape=config.shape
    cpus=config.instance_pool_ocpus
    memory=config.instance_pool_memory
    hostname_convention=config.hostname_convention
    RDMA=config.rdma_enabled
    mkplace=config.use_marketplace_image
    marketplace_listing=config.marketplace_listing

    if mkplace:
        image_id = get_marketplace_image(marketplace_listing, target_compartment_id)

    with open("/config/key/public", "r") as file:
        public_key = file.read()
    with open("/config/bin/cloud-init.sh", "r") as file:
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

        if config.role == "login":
            new_create_vnic = oci.core.models.CreateVnicDetails(
                assign_public_ip=True,
                subnet_id=subnet_id
                # Additional fields can be added here if needed
                )
        else:
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

        legacy_imds_off = oci.core.models.InstanceOptions(are_legacy_imds_endpoints_disabled = True)

        if hostname is None:
            new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+cluster_name
            new_tags={"cluster_name" : cluster_name, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}
        else:
            new_display_name=hostname
            new_tags={"cluster_name" : cluster_name, "controller_name" : controller_hostname}
        if config.role == "login":
            new_tags["login"]="true"
        new_tags = _add_config_fss_hostname_tag(new_tags)
        if shape.endswith("Flex"):
            new_launch_details = oci.core.models.LaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=target_compartment_id,
            shape=shape,
            shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=cpus,memory_in_gbs=memory),
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details,
            compute_cluster_id=cn_ocid,
            display_name=new_display_name,
            instance_options = legacy_imds_off,
            )
        else:
            new_launch_details = oci.core.models.LaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=target_compartment_id,
            shape=shape,
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details,
            compute_cluster_id=cn_ocid,
            display_name=new_display_name,
            instance_options = legacy_imds_off,
            )
        return new_launch_details
    except oci.exceptions.ServiceError as e:
        logger.error(f"An error occurred: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None

# def create_instance_configuration_from_another(instance_config_ocid, memory_cluster_name):
#     """
#     Creates a new instance configuration by fully replicating the source configuration with a new memory_cluster
#     """

#     src_config = CLIENTS.compute_management_client.get_instance_configuration(instance_config_ocid).data
#     launch = src_config.instance_details.launch_details

#     # Update metadata with new SSH key; create a copy if it exists.
#     new_metadata = dict(launch.metadata) if launch.metadata else {}

#     # Build Agent Config if present
#     new_agent_config = None
#     if launch.agent_config:
#         new_agent_config = oci.core.models.InstanceConfigurationLaunchInstanceAgentConfigDetails(
#             are_all_plugins_disabled=launch.agent_config.are_all_plugins_disabled,
#             is_management_disabled=launch.agent_config.is_management_disabled,
#             is_monitoring_disabled=launch.agent_config.is_monitoring_disabled,
#             plugins_config=[
#                 oci.core.models.InstanceAgentPluginConfigDetails(
#                     desired_state=plugin.desired_state,
#                     name=plugin.name
#                 ) for plugin in (launch.agent_config.plugins_config or [])
#             ]
#         )

#     # Build Create VNIC Details if present
#     new_create_vnic = None
#     if launch.create_vnic_details:
#         new_create_vnic = oci.core.models.InstanceConfigurationCreateVnicDetails(
#             assign_public_ip=launch.create_vnic_details.assign_public_ip,
#             assign_private_dns_record=launch.create_vnic_details.assign_private_dns_record,
#             subnet_id=launch.create_vnic_details.subnet_id
#             # Additional fields can be added here if needed
#         )

#     # Build Source Details
#     src_details = launch.source_details
#     bv_size=getattr(src_details, 'boot_volume_size_in_gbs', None)
#     image_id=src_details.image_id

#     new_source_details = oci.core.models.InstanceConfigurationInstanceSourceViaImageDetails(
#         source_type=src_details.source_type,
#         image_id=image_id,
#         boot_volume_size_in_gbs=bv_size,
#         boot_volume_vpus_per_gb=getattr(src_details, 'boot_volume_vpus_per_gb', None)
#     )

#     new_tags=launch.freeform_tags
#     # Build new Launch Details copying as many fields as possible
#     new_launch_details = oci.core.models.InstanceConfigurationLaunchInstanceDetails(
#         availability_domain=launch.availability_domain,
#         compartment_id=launch.compartment_id,
#         display_name=launch.display_name,
#         shape=launch.shape,
#         shape_config=launch.shape_config,
#         platform_config=launch.platform_config,
#         metadata=new_metadata,
#         extended_metadata=launch.extended_metadata,
#         ipxe_script=launch.ipxe_script,
#         freeform_tags=new_tags,
#         defined_tags=launch.defined_tags,
#         agent_config=new_agent_config,
#         create_vnic_details=new_create_vnic,
#         source_details=new_source_details,
#         security_attributes=launch.security_attributes,
#         launch_options=launch.launch_options,
#         fault_domain=launch.fault_domain,
#         dedicated_vm_host_id=launch.dedicated_vm_host_id,
#         launch_mode=launch.launch_mode,
#         instance_options=launch.instance_options,
#         availability_config=launch.availability_config,
#         preemptible_instance_config=launch.preemptible_instance_config,
#         licensing_configs=launch.licensing_configs
#     )

#     # Build new Instance Details
#     new_instance_details = oci.core.models.ComputeInstanceDetails(
#         instance_type=src_config.instance_details.instance_type,
#         launch_details=new_launch_details,
#         block_volumes=src_config.instance_details.block_volumes,
#         secondary_vnics=src_config.instance_details.secondary_vnics
#     )

#     # Construct new Instance Configuration Details object
#     new_config_details = oci.core.models.CreateInstanceConfigurationDetails(
#         compartment_id=src_config.compartment_id,
#         display_name=src_config.display_name + "-copy",
#         instance_details=new_instance_details,
#         defined_tags=src_config.defined_tags,
#         freeform_tags=src_config.freeform_tags
#     )

#     response = CLIENTS.compute_management_client.create_instance_configuration(new_config_details)
#     return response.data

def generate_instance_config(config, controller_hostname, cluster_name, memory_cluster_name=None):
    subnet_id=config.private_subnet_id
    image_id=config.image_id
    bv_size=config.boot_volume_size
    availability_domain=config.availability_domain
    target_compartment_id=config.target_compartment_id
    shape=config.shape
    cpus=config.instance_pool_ocpus
    memory=config.instance_pool_memory
    hostname_convention=config.hostname_convention
    RDMA=config.rdma_enabled
    mkplace=config.use_marketplace_image
    marketplace_listing=config.marketplace_listing

    if mkplace:
        image_id = get_marketplace_image(marketplace_listing, target_compartment_id)

    with open("/config/key/public", "r") as file:
        public_key = file.read()
    with open("/config/bin/cloud-init.sh", "r") as file:
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
        legacy_imds_off = oci.core.models.InstanceConfigurationInstanceOptions(are_legacy_imds_endpoints_disabled = True)

        new_metadata={"ssh_authorized_keys":public_key,"user_data": cloud_init}
        new_tags={"cluster_name" : cluster_name, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}
        new_tags = _add_config_fss_hostname_tag(new_tags)
        if shape.endswith("Flex"):
            new_launch_details = oci.core.models.InstanceConfigurationLaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=target_compartment_id,
            shape=shape,
            shape_config=oci.core.models.InstanceConfigurationLaunchInstanceShapeConfigDetails(ocpus=cpus,memory_in_gbs=memory),
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details,
            instance_options = legacy_imds_off,
            )
        else:
            new_launch_details = oci.core.models.InstanceConfigurationLaunchInstanceDetails(
            availability_domain=availability_domain,
            compartment_id=target_compartment_id,
            shape=shape,
            metadata=new_metadata,
            freeform_tags=new_tags,
            agent_config=new_agent_config,
            create_vnic_details=new_create_vnic,
            source_details=new_source_details,
            instance_options = legacy_imds_off,
            )


        # Build new Instance Details
        new_instance_details = oci.core.models.ComputeInstanceDetails(
            instance_type="compute",
            launch_details=new_launch_details
        )

        # Construct new Instance Configuration Details object
        new_config_details = oci.core.models.CreateInstanceConfigurationDetails(
            compartment_id=target_compartment_id,
            display_name= cluster_name,
            instance_details=new_instance_details
        )

        create_response = CLIENTS.compute_management_client.create_instance_configuration(new_config_details).data
        # Check that the instance config can be queried.
        for i in range(10):
            try:
                create_response=CLIENTS.compute_management_client.get_instance_configuration(create_response.id).data
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

def _dedupe_by_id(items):
    deduped = []
    seen = set()
    for item in items:
        item_id = getattr(item, "id", None)
        if not item_id or item_id in seen:
            continue
        deduped.append(item)
        seen.add(item_id)
    return deduped

def _response_items(data):
    if data is None:
        return []
    items = getattr(data, "items", None)
    if items is not None and not callable(items):
        return items
    return data

def _resolve_compute_gpu_memory_clusters(memory_cluster_id=None, nodes=None):
    nodes = nodes or []
    memory_cluster_ids = []

    if memory_cluster_id:
        memory_cluster_ids.append(memory_cluster_id)
    else:
        memory_cluster_ids.extend(
            sorted({
                node.memory_cluster_id
                for node in nodes
                if getattr(node, "memory_cluster_id", None)
                and node.memory_cluster_id != "None"
            })
        )

    if not memory_cluster_ids:
        return []

    compartments = {
        node.compartment_id
        for node in nodes
        if getattr(node, "compartment_id", None)
    }
    controller = get_controller_node()
    if controller and getattr(controller, "compartment_id", None):
        compartments.add(controller.compartment_id)

    memory_clusters = []
    for cluster_id_or_name in memory_cluster_ids:
        try:
            memory_clusters.append(
                CLIENTS.compute_client.get_compute_gpu_memory_cluster(cluster_id_or_name).data
            )
            continue
        except oci.exceptions.ServiceError as exc:
            if exc.status != 404:
                raise

        matches = []
        for compartment_id in compartments:
            response = oci.pagination.list_call_get_all_results(
                CLIENTS.compute_client.list_compute_gpu_memory_clusters,
                compartment_id=compartment_id,
                display_name=cluster_id_or_name,
            )
            matches.extend([
                cluster for cluster in _response_items(response.data)
                if cluster.id == cluster_id_or_name or cluster.display_name == cluster_id_or_name
            ])

        if not matches:
            logger.warning("No compute GPU memory cluster found for %s", cluster_id_or_name)
            continue

        memory_clusters.extend(matches)

    return _dedupe_by_id(memory_clusters)

def _memory_cluster_lookup_compartments(nodes=None):
    nodes = nodes or []
    compartments = {
        node.compartment_id
        for node in nodes
        if getattr(node, "compartment_id", None)
    }
    controller = get_controller_node()
    if controller and getattr(controller, "compartment_id", None):
        compartments.add(controller.compartment_id)
    for config in get_all_configs("all"):
        if getattr(config, "target_compartment_id", None):
            compartments.add(config.target_compartment_id)
    return compartments

def _list_compute_gpu_memory_clusters(compartments, display_name=None):
    memory_clusters = []
    for compartment_id in compartments:
        kwargs = {"compartment_id": compartment_id}
        if display_name:
            kwargs["display_name"] = display_name
        response = oci.pagination.list_call_get_all_results(
            CLIENTS.compute_client.list_compute_gpu_memory_clusters,
            **kwargs,
        )
        memory_clusters.extend(_response_items(response.data))
    return _dedupe_by_id(memory_clusters)

def _list_compute_gpu_memory_fabrics_for_delete():
    controller = get_controller_node()
    if controller is None or not getattr(controller, "tenancy_id", None):
        logger.error("Cannot resolve GPU memory fabrics without a controller node in the database")
        sys.exit(1)

    return oci.pagination.list_call_get_all_results(
        CLIENTS.compute_client.list_compute_gpu_memory_fabrics,
        compartment_id=controller.tenancy_id,
    ).data

def _resolve_compute_gpu_memory_clusters_by_fabric_scope(
    compartments,
    compute_local_block_id=None,
    compute_network_block_id=None,
    compute_hpc_island_id=None,
):
    fabrics = [
        fabric for fabric in _list_compute_gpu_memory_fabrics_for_delete()
        if _memory_fabric_matches_scope(
            fabric,
            compute_local_block_id=compute_local_block_id,
            compute_network_block_id=compute_network_block_id,
            compute_hpc_island_id=compute_hpc_island_id,
        )
    ]
    if not fabrics:
        logger.error("No GPU memory fabrics found for the requested scope")
        sys.exit(1)

    fabric_ids = {fabric.id for fabric in fabrics}
    matches = [
        cluster for cluster in _list_compute_gpu_memory_clusters(compartments)
        if getattr(cluster, "gpu_memory_fabric_id", None) in fabric_ids
    ]
    if not matches:
        logger.error("No compute GPU memory clusters found for the requested fabric scope")
        sys.exit(1)

    logger.info(
        "Resolved fabric scope to memory cluster(s): %s",
        ", ".join(cluster.display_name or cluster.id for cluster in matches),
    )
    return matches

def resolve_compute_gpu_memory_cluster_delete_targets(
    targets,
    nodes=None,
    compute_local_block_id=None,
    compute_network_block_id=None,
    compute_hpc_island_id=None,
):
    targets = targets or []
    nodes = nodes or []
    compartments = _memory_cluster_lookup_compartments(nodes)
    memory_clusters = []

    if compute_local_block_id or compute_network_block_id or compute_hpc_island_id:
        memory_clusters.extend(
            _resolve_compute_gpu_memory_clusters_by_fabric_scope(
                compartments,
                compute_local_block_id=compute_local_block_id,
                compute_network_block_id=compute_network_block_id,
                compute_hpc_island_id=compute_hpc_island_id,
            )
        )

    for target in targets:
        if target.startswith("ocid1.computegpumemoryfabric."):
            matches = [
                cluster for cluster in _list_compute_gpu_memory_clusters(compartments)
                if getattr(cluster, "gpu_memory_fabric_id", None) == target
            ]
            if not matches:
                logger.error(f"No compute GPU memory clusters found for GPU memory fabric {target}")
                sys.exit(1)
            logger.info(
                "Resolved GPU memory fabric %s to memory cluster(s): %s",
                target,
                ", ".join(cluster.display_name or cluster.id for cluster in matches),
            )
            memory_clusters.extend(matches)
            continue

        matches = _resolve_compute_gpu_memory_clusters(memory_cluster_id=target, nodes=nodes)
        if not matches:
            logger.error(f"No compute GPU memory cluster found for {target}")
            sys.exit(1)
        memory_clusters.extend(matches)

    return _dedupe_by_id(memory_clusters)

def _create_updated_instance_config(
    compute_mgmt,
    src_config,
    image_id=None,
    ssh_key=None,
    cloud_init_path=None,
    boot_volume_size=None,
    new_display_name=None,
):
    launch = src_config.instance_details.launch_details

    new_metadata = dict(launch.metadata) if launch.metadata else {}

    if ssh_key:
        new_metadata["ssh_authorized_keys"] = ssh_key

    if cloud_init_path:
        new_metadata["user_data"] = oci.util.file_content_as_launch_instance_user_data(
            cloud_init_path
        )

    new_agent_config = None
    if launch.agent_config:
        new_agent_config = oci.core.models.InstanceConfigurationLaunchInstanceAgentConfigDetails(
            are_all_plugins_disabled=launch.agent_config.are_all_plugins_disabled,
            is_management_disabled=launch.agent_config.is_management_disabled,
            is_monitoring_disabled=launch.agent_config.is_monitoring_disabled,
            plugins_config=[
                oci.core.models.InstanceAgentPluginConfigDetails(
                    desired_state=plugin.desired_state,
                    name=plugin.name,
                )
                for plugin in (launch.agent_config.plugins_config or [])
            ],
        )

    new_create_vnic = None
    if launch.create_vnic_details:
        new_create_vnic = oci.core.models.InstanceConfigurationCreateVnicDetails(
            assign_public_ip=launch.create_vnic_details.assign_public_ip,
            assign_private_dns_record=launch.create_vnic_details.assign_private_dns_record,
            subnet_id=launch.create_vnic_details.subnet_id,
            nsg_ids=launch.create_vnic_details.nsg_ids,
            assign_ipv6_ip=launch.create_vnic_details.assign_ipv6_ip,
        )

    src_details = launch.source_details

    final_image_id = image_id if image_id else src_details.image_id
    final_bv_size = (
        boot_volume_size
        if boot_volume_size
        else getattr(src_details, "boot_volume_size_in_gbs", None)
    )

    new_source_details = oci.core.models.InstanceConfigurationInstanceSourceViaImageDetails(
        source_type="image",
        image_id=final_image_id,
        boot_volume_size_in_gbs=final_bv_size,
        boot_volume_vpus_per_gb=getattr(
            src_details, "boot_volume_vpus_per_gb", None
        ),
    )

    new_launch_details = oci.core.models.InstanceConfigurationLaunchInstanceDetails(
        availability_domain=launch.availability_domain,
        compartment_id=launch.compartment_id,
        display_name=launch.display_name,
        shape=launch.shape,
        shape_config=launch.shape_config,
        platform_config=launch.platform_config,
        metadata=new_metadata,
        extended_metadata=launch.extended_metadata,
        ipxe_script=launch.ipxe_script,
        freeform_tags=launch.freeform_tags,
        defined_tags=launch.defined_tags,
        agent_config=new_agent_config,
        create_vnic_details=new_create_vnic,
        source_details=new_source_details,
        security_attributes=launch.security_attributes,
        launch_options=launch.launch_options,
        fault_domain=launch.fault_domain,
        dedicated_vm_host_id=launch.dedicated_vm_host_id,
        launch_mode=launch.launch_mode,
        instance_options=launch.instance_options,
        availability_config=launch.availability_config,
        preemptible_instance_config=launch.preemptible_instance_config,
        licensing_configs=launch.licensing_configs,
        is_pv_encryption_in_transit_enabled=launch.is_pv_encryption_in_transit_enabled,
    )

    new_instance_details = oci.core.models.ComputeInstanceDetails(
        instance_type=src_config.instance_details.instance_type,
        launch_details=new_launch_details,
        block_volumes=src_config.instance_details.block_volumes,
        secondary_vnics=src_config.instance_details.secondary_vnics,
    )

    final_display_name = (
        new_display_name
        if new_display_name
        else f"{src_config.display_name}-updated"
    )

    new_config_details = oci.core.models.CreateInstanceConfigurationDetails(
        compartment_id=src_config.compartment_id,
        display_name=final_display_name,
        instance_details=new_instance_details,
        defined_tags=src_config.defined_tags,
        freeform_tags=src_config.freeform_tags,
    )

    return compute_mgmt.create_instance_configuration(new_config_details).data

def _instance_config_display_name_for_update(
    new_display_name,
    current_config_id,
    src_config,
    multiple_source_configs=False,
):
    if not new_display_name:
        return None
    if not multiple_source_configs:
        return new_display_name

    source_name = getattr(src_config, "display_name", None) or current_config_id[-8:]
    source_suffix = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(source_name)).strip("-")
    if not source_suffix:
        source_suffix = current_config_id[-8:]
    return f"{new_display_name}-{source_suffix}"

def update_instance_config(
    cluster_name,
    image_id=None,
    ssh_key=None,
    cloud_init_path=None,
    boot_volume_size=None,
    new_display_name=None,
    memory_cluster_id=None,
    existing_instance_config_id=None,
):
    """
    Update the instance configuration used by a cluster.

    - Creates a new instance configuration based on the current one, unless
      an existing instance configuration OCID is provided
    - Overrides image / ssh key / cloud-init / boot volume size if provided
    - Updates an IPA/CN instance pool, a single GMC, or all GMCs in a CC
    """

    compute_mgmt = CLIENTS.compute_management_client
    compute_mgmt_composite = CLIENTS.compute_management_client_composite_operations

    # -------------------------------------------------------
    # STEP 1: Resolve cluster / GMC targets from DB
    # -------------------------------------------------------
    nodes = get_nodes_by_cluster(cluster_name) if cluster_name else []

    resolved_memory_cluster_id = memory_cluster_id
    if not nodes and cluster_name and not memory_cluster_id:
        memory_cluster_nodes = get_nodes_by_memory_cluster(cluster_name)
        if memory_cluster_nodes:
            nodes = memory_cluster_nodes
            resolved_memory_cluster_id = cluster_name

    memory_clusters = _resolve_compute_gpu_memory_clusters(
        memory_cluster_id=resolved_memory_cluster_id,
        nodes=nodes,
    )

    if memory_clusters:
        logger.info(
            "Updating %s compute GPU memory cluster(s): %s",
            len(memory_clusters),
            ", ".join(cluster.display_name or cluster.id for cluster in memory_clusters),
        )
        if existing_instance_config_id:
            compute_mgmt.get_instance_configuration(existing_instance_config_id)
            logger.info(
                "Using existing instance config for GMC update: %s",
                existing_instance_config_id,
            )

        updated_configs = {}
        created_config_by_source = {}
        source_config_ids = {
            cluster.instance_configuration_id
            for cluster in memory_clusters
            if getattr(cluster, "instance_configuration_id", None)
        }
        multiple_source_configs = len(source_config_ids) > 1
        for memory_cluster in memory_clusters:
            current_config_id = memory_cluster.instance_configuration_id
            logger.info(
                "Current instance config for GMC %s: %s",
                memory_cluster.display_name or memory_cluster.id,
                current_config_id,
            )
            if existing_instance_config_id:
                target_config_id = existing_instance_config_id
            elif current_config_id in created_config_by_source:
                target_config_id = created_config_by_source[current_config_id]
                logger.info(
                    "Reusing instance config %s for GMC %s; source config %s was already updated",
                    target_config_id,
                    memory_cluster.display_name or memory_cluster.id,
                    current_config_id,
                )
            else:
                src_config = compute_mgmt.get_instance_configuration(current_config_id).data
                effective_display_name = _instance_config_display_name_for_update(
                    new_display_name,
                    current_config_id,
                    src_config,
                    multiple_source_configs=multiple_source_configs,
                )
                new_config = _create_updated_instance_config(
                    compute_mgmt,
                    src_config,
                    image_id=image_id,
                    ssh_key=ssh_key,
                    cloud_init_path=cloud_init_path,
                    boot_volume_size=boot_volume_size,
                    new_display_name=effective_display_name,
                )
                target_config_id = new_config.id
                created_config_by_source[current_config_id] = target_config_id
                logger.info(
                    "Created instance config %s from source config %s",
                    target_config_id,
                    current_config_id,
                )

            if current_config_id == target_config_id:
                updated_configs[memory_cluster.id] = target_config_id
                logger.info(
                    "Skipping GMC %s; instance config is already %s",
                    memory_cluster.display_name or memory_cluster.id,
                    target_config_id,
                )
                continue

            update_details = oci.core.models.UpdateComputeGpuMemoryClusterDetails(
                instance_configuration_id=target_config_id
            )
            CLIENTS.compute_client.update_compute_gpu_memory_cluster(
                memory_cluster.id,
                update_details,
            )
            updated_configs[memory_cluster.id] = target_config_id
            logger.info(
                "Updated GMC %s to instance config %s",
                memory_cluster.display_name or memory_cluster.id,
                target_config_id,
            )

        logger.info("Compute GPU memory cluster instance configuration update complete")
        if len(updated_configs) == 1:
            return next(iter(updated_configs.values()))
        return updated_configs

    if not nodes:
        logger.error(f"No nodes found for cluster or GMC {cluster_name or memory_cluster_id}")
        sys.exit(1)

    first_node = nodes[0]
    cluster_type, cluster_ocid, ipa_ocid = get_instance_type(first_node)

    if cluster_type not in ["IPA", "CN"]:
        logger.error("Instance configuration update is supported only for IPA, CN, or GMC-backed clusters")
        sys.exit(1)

    # -------------------------------------------------------
    # STEP 2: Resolve instance pool ID
    # -------------------------------------------------------
    if cluster_type == "IPA":
        instance_pool_id = ipa_ocid

    elif cluster_type == "CN":
        cluster_network = compute_mgmt.get_cluster_network(cluster_ocid).data

        if not cluster_network.instance_pools:
            logger.error("No instance pool found in cluster network")
            sys.exit(1)

        if len(cluster_network.instance_pools) > 1:
            logger.error(
                f"Cluster network {cluster_name} returned multiple instance pools, "
                "but OCI supports only one."
            )
            sys.exit(1)

        instance_pool_id = cluster_network.instance_pools[0].id

    logger.info(f"Using instance pool: {instance_pool_id}")

    # -------------------------------------------------------
    # STEP 3: Use first pool to get current config
    # -------------------------------------------------------
    pool = compute_mgmt.get_instance_pool(instance_pool_id).data
    current_config_id = pool.instance_configuration_id

    logger.info(f"Current instance config: {current_config_id}")

    if existing_instance_config_id:
        compute_mgmt.get_instance_configuration(existing_instance_config_id)
        new_config_id = existing_instance_config_id
        logger.info(f"Using existing instance config: {new_config_id}")
    else:
        src_config = compute_mgmt.get_instance_configuration(
            current_config_id
        ).data

        new_config = _create_updated_instance_config(
            compute_mgmt,
            src_config,
            image_id=image_id,
            ssh_key=ssh_key,
            cloud_init_path=cloud_init_path,
            boot_volume_size=boot_volume_size,
            new_display_name=new_display_name,
        )

        new_config_id = new_config.id
        logger.info(f"New instance config created: {new_config_id}")

    # -------------------------------------------------------
    # STEP 11: Update ALL instance pools safely (with waiter)
    # -------------------------------------------------------

    if current_config_id == new_config_id:
        logger.info(
            "Skipping instance pool %s; instance config is already %s",
            instance_pool_id,
            new_config_id,
        )
        logger.info("Cluster instance configuration update complete")
        return new_config_id

    logger.info(f"Updating instance pool {instance_pool_id}")

    update_details = oci.core.models.UpdateInstancePoolDetails(
        instance_configuration_id=new_config_id
    )

    compute_mgmt_composite.update_instance_pool_and_wait_for_state(
        instance_pool_id,
        update_details,
        wait_for_states=["RUNNING"],
        waiter_kwargs={"max_wait_seconds": 3600},
    )

    logger.info(f"Instance pool {instance_pool_id} updated successfully")
    logger.info("Cluster instance configuration update complete")

    return new_config_id

def generate_inventory(config,cluster_name):

    original_inventory="/config/playbooks/inventory"
    inventory_name=f"/config/playbooks/inventory_{cluster_name}"
    modifications={"cluster_name":cluster_name,
                "shape":config.shape,
                "rdma_enabled":config.rdma_enabled,
                "queue":config.partition,
                "permanent":str(config.permanent).lower(),
                "instance_type": config.name,
                "hostname_convention": config.hostname_convention,
                "hyperthreading": config.hyperthreading,
                "private_subnet_id": config.private_subnet_id,
                "private_subnet": config.private_subnet_cidr
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
        logger.error(f"The inventory file {original_inventory} was not found.")
    except Exception as e:
        logger.error(f"{e}")

def remove_inventory(cluster_name):
    inventory_name=f"/config/playbooks/inventory_{cluster_name}"
    if os.path.exists(inventory_name):
        os.remove(inventory_name)
        logger.info(f"Inventory {inventory_name} deleted successfully.")
    else:
        logger.warning(f"Inventory {inventory_name} was not present.")

def create_cluster(config, count, cluster_name, controller_hostname, names, gpu_memory_fabric=None, gpu_memory_cluster_name=None, targetsize=0, gpu_memory_fabrics=None):
    generate_inventory(config, cluster_name)
    if gpu_memory_fabrics is None and gpu_memory_fabric is not None:
        gpu_memory_fabrics = [{
            "ocid": gpu_memory_fabric,
            "count": count,
            "name": gpu_memory_cluster_name,
            "targetsize": targetsize,
        }]

    if not config.stand_alone or "GPU.GB" in config.shape:
        instance_config_data=generate_instance_config(config, controller_hostname, cluster_name, memory_cluster_name = gpu_memory_cluster_name)
        instance_config_ocid=instance_config_data.id

        if config.rdma_enabled:
            if "GPU.GB" in config.shape:
                if not gpu_memory_fabrics:
                    logger.error("For BM.GPU.GB200.4 or BM.GPU.GB200-v2.4 or BM.GPU.GB200-v3.4 or BM.GPU.GB300.4, the memory fabric needs to be specified, Exiting")
                    sys.exit(1)
                cc_details=oci.core.models.CreateComputeClusterDetails(compartment_id=config.target_compartment_id,availability_domain=config.availability_domain,display_name=cluster_name)
                cn = CLIENTS.compute_client.create_compute_cluster(create_compute_cluster_details=cc_details).data
                cn_id=cn.id
                for fabric_target in gpu_memory_fabrics:
                    fabric_id = fabric_target.get("ocid")
                    fabric_count = int(fabric_target.get("count", count))
                    memory_cluster_name = fabric_target.get("name") or f"{cluster_name}_{fabric_id[-5:]}"
                    fabric_targetsize = int(fabric_target.get("targetsize", targetsize) or 0)
                    if fabric_targetsize != 0:
                        clusterScaleConfig=oci.core.models.CreateComputeGpuMemoryClusterScaleConfig(is_downsize_enabled=True, is_upsize_enabled=True, target_size=fabric_targetsize)
                        compute_gpu_memory_cluster_details=oci.core.models.CreateComputeGpuMemoryClusterDetails(
                            availability_domain=config.availability_domain,
                            compartment_id=config.target_compartment_id,
                            compute_cluster_id=cn_id,
                            instance_configuration_id=instance_config_ocid,
                            size=fabric_count,
                            gpu_memory_fabric_id=fabric_id,
                            display_name=memory_cluster_name,
                            gpu_memory_cluster_scale_config=clusterScaleConfig)
                        try:
                            CLIENTS.compute_client.create_compute_gpu_memory_cluster(compute_gpu_memory_cluster_details)
                        except:
                            logger.error("Failed to create compute GPU memory cluster, you specified a non-0 target size. Are you whitelisted for it? ")
                            sys.exit(1)
                    else:
                        compute_gpu_memory_cluster_details=oci.core.models.CreateComputeGpuMemoryClusterDetails(
                            availability_domain=config.availability_domain,
                            compartment_id=config.target_compartment_id,
                            compute_cluster_id=cn_id,
                            instance_configuration_id=instance_config_ocid,
                            size=fabric_count,
                            gpu_memory_fabric_id=fabric_id,
                            display_name=memory_cluster_name)
                        CLIENTS.compute_client.create_compute_gpu_memory_cluster(compute_gpu_memory_cluster_details)
            else:
                ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=config.private_subnet_id)
                ip_placement_details=oci.core.models.ClusterNetworkPlacementConfigurationDetails(availability_domain=config.availability_domain,primary_vnic_subnets=ip_placement_subnet_details)
                instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails(display_name=cluster_name,instance_configuration_id=instance_config_ocid,size=count)
                cn_details=oci.core.models.CreateClusterNetworkDetails(compartment_id=config.target_compartment_id,display_name=cluster_name,instance_pools=[instance_pools_details],placement_configuration=ip_placement_details)
                cn = CLIENTS.compute_management_client_composite_operations.create_cluster_network_and_wait_for_state(create_cluster_network_details=cn_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})
        else:
            ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=config.private_subnet_id)
            ip_placement_details=oci.core.models.CreateInstancePoolPlacementConfigurationDetails(availability_domain=config.availability_domain,primary_vnic_subnets=ip_placement_subnet_details)
            instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails()
            ip_details=oci.core.models.CreateInstancePoolDetails(compartment_id=config.target_compartment_id,display_name=cluster_name,placement_configurations=[ip_placement_details],instance_configuration_id=instance_config_ocid,size=count)
            cn = CLIENTS.compute_management_client_composite_operations.create_instance_pool_and_wait_for_state(create_instance_pool_details=ip_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})

    else:
        if config.rdma_enabled:
            cc_details=oci.core.models.CreateComputeClusterDetails(compartment_id=config.target_compartment_id,availability_domain=config.availability_domain,display_name=cluster_name)
            cn = CLIENTS.compute_client.create_compute_cluster(create_compute_cluster_details=cc_details).data
            cn_id=cn.id
        else:
            cn_id=None
        for i in range(count):
            launch_instance_details = getLaunchInstanceDetailsFromInstanceType(config, controller_hostname, cn_id, cluster_name, hostname=names[i])
            CLIENTS.compute_client_composite_operations.launch_instance_and_wait_for_state(launch_instance_details)

def create_login_nodes(config, count, controller_hostname, cluster_name, names):
    for i in range(count):
        launch_instance_details = getLaunchInstanceDetailsFromInstanceType(config, controller_hostname, None, cluster_name, hostname=names[i])
        CLIENTS.compute_client_composite_operations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])

def delete_cluster(cluster_name,nodes_list):
    cluster_type,cluster_ocid,ipa_ocid = get_instance_type(nodes_list[0])
    if cluster_type == "CN":
        CLIENTS.compute_management_client.terminate_cluster_network(cluster_ocid)
    elif cluster_type == "IPA":
        CLIENTS.compute_management_client.terminate_instance_pool(cluster_ocid)
    elif cluster_type == "CC" or cluster_type == "SA":
        for instance in nodes_list:
            if hasattr(CLIENTS.compute_client_composite_operations, "terminate_instance_and_wait_for_work_request"):
                CLIENTS.compute_client_composite_operations.terminate_instance_and_wait_for_work_request(instance.ocid,work_request_states=["STATUS_SUCCEEDED"],waiter_kwargs={'max_wait_seconds': 600})
            else:
                CLIENTS.compute_client_composite_operations.terminate_instance_and_wait_for_state(instance.ocid,wait_for_states=["TERMINATING", "TERMINATED"],waiter_kwargs={'max_wait_seconds':  600})
        instance_running=True
        while instance_running:
            instance_running=False
            for instance in nodes_list:
                if CLIENTS.compute_client.get_instance(instance.ocid).data.lifecycle_state != "TERMINATED":
                    instance_running=True
                    time.sleep(30)
        if cluster_type == "CC":
            CLIENTS.compute_client.delete_compute_cluster(cluster_ocid)
    elif cluster_type == "MC":
        logger.error("A BM.GPU.GB200.4, BM.GPU.GB200-v2.4, BM.GPU.GB200-v2.4, or BM.GPU.GB300.4 instance should not be calling this function")
    remove_inventory(cluster_name)

def get_memory_fabrics(tenancy_id, compartment_id):
    """
    Helper: Build a list of lists [gmf_data, current_usage_in_compartment, gmcs, host_type_count]
    from all ACTIVE compute GPU memory clusters in the given compartment.
    """
    fabric_list = []
    memory_clusters = oci.pagination.list_call_get_all_results(
                CLIENTS.compute_client.list_compute_gpu_memory_clusters,
                compartment_id = compartment_id
            ).data
    memory_fabric_usage = {}

    for memory_cluster in memory_clusters:
        if memory_cluster.lifecycle_state != "ACTIVE":
            continue
        gmf_id = memory_cluster.gpu_memory_fabric_id
        if  gmf_id in memory_fabric_usage.keys():
            memory_fabric_usage[gmf_id][0] += memory_cluster.size
            memory_fabric_usage[gmf_id][1][memory_cluster.id] = memory_cluster.display_name
        else:
            memory_fabric_usage[gmf_id] = [
                        memory_cluster.size,
                        {memory_cluster.id: memory_cluster.display_name}
                ]
    host_api_list = get_host_api_dict(compartment_id, tenancy_id)

    lifecycle_states = set([entry.lifecycle_state for entry in host_api_list])

    for fabric in oci.pagination.list_call_get_all_results(
            CLIENTS.compute_client.list_compute_gpu_memory_fabrics,
            compartment_id=tenancy_id).data:
        if fabric.id in memory_fabric_usage.keys():
            size = memory_fabric_usage[fabric.id][0]
            memory_clusters = memory_fabric_usage[fabric.id][1]
        else:
            size = 0
            memory_clusters = {}
        host_type_count = {key: 0 for key in lifecycle_states}
        available_shape_count = {}
        try:
            for host in host_api_list:
                if host.gpu_memory_fabric_id == fabric.id:
                    host_type_count[host.lifecycle_state] += 1
                    if host.lifecycle_state == "AVAILABLE":
                        available_shape_count[host.shape] = available_shape_count.get(host.shape, 0) + 1
        except:
            logger.warning("Host API is not available")
        fabric_list.append([fabric, size, memory_clusters, host_type_count, available_shape_count])

    return fabric_list


# Fabric item is a list containing:
# [fabric, size, memory_clusters, host_type_count, available_shape_count]
def _memory_fabric_available_count(fabric_item):
    fabric_api_available_count = getattr(fabric_item[0], "available_host_count", 0)
    try:
        host_api_available_count = int(fabric_item[3].get("AVAILABLE", 0) or 0)
    except (TypeError, ValueError, AttributeError):
        host_api_available_count = 0

    if host_api_available_count > 0:
        return host_api_available_count

    try:
        return int(fabric_api_available_count or 0)
    except (TypeError, ValueError):
        return 0


def _memory_fabric_matches_scope(
    fabric,
    compute_local_block_id=None,
    compute_network_block_id=None,
    compute_hpc_island_id=None,
):
    expected_values = {
        "compute_local_block_id": compute_local_block_id,
        "compute_network_block_id": compute_network_block_id,
        "compute_hpc_island_id": compute_hpc_island_id,
    }
    for attr, expected_value in expected_values.items():
        if expected_value and getattr(fabric, attr, None) != expected_value:
            return False
    return True

def _get_memory_fabric_targets_by_id(tenancy_id, fabric_ids):
    fabrics = oci.pagination.list_call_get_all_results(
        CLIENTS.compute_client.list_compute_gpu_memory_fabrics,
        compartment_id=tenancy_id,
    ).data
    fabric_by_id = {fabric.id: fabric for fabric in fabrics}
    targets = []

    for fabric_id in fabric_ids or []:
        fabric = fabric_by_id.get(fabric_id)
        if fabric is None:
            logger.error(f"GPU memory fabric {fabric_id} was not found")
            sys.exit(1)
        targets.append({
            "ocid": fabric.id,
            "available": getattr(fabric, "available_host_count", 0) or 0,
            "memory_clusters": {},
            "fabric": fabric,
            "compute_hpc_island_id": getattr(fabric, "compute_hpc_island_id", None),
        })

    return targets

def get_available_memory_fabric_targets(
    tenancy_id,
    compartment_id,
    fabric_ids=None,
    all_available=False,
    compute_local_block_id=None,
    compute_network_block_id=None,
    compute_hpc_island_id=None,
):
    """
    Return launch targets using the same data source as `mgmt fabrics list`.
    For all_available, only unused fabrics with AVAILABLE hosts are returned.
    """
    if fabric_ids and not all_available:
        return _get_memory_fabric_targets_by_id(tenancy_id, fabric_ids)

    fabric_list = get_memory_fabrics(tenancy_id, compartment_id)
    fabric_by_id = {fabric_item[0].id: fabric_item for fabric_item in fabric_list}

    if all_available:
        selected = [
            fabric_item for fabric_item in fabric_list
            if str(getattr(fabric_item[0], "lifecycle_state", "")).upper() == "AVAILABLE"
            and not fabric_item[2]
            and _memory_fabric_available_count(fabric_item) > 0
            and _memory_fabric_matches_scope(
                fabric_item[0],
                compute_local_block_id=compute_local_block_id,
                compute_network_block_id=compute_network_block_id,
                compute_hpc_island_id=compute_hpc_island_id,
            )
        ]
        selected.sort(key=_memory_fabric_available_count, reverse=True)
    else:
        selected = []
        for fabric_id in fabric_ids or []:
            fabric_item = fabric_by_id.get(fabric_id)
            if fabric_item is None:
                logger.error(f"GPU memory fabric {fabric_id} was not found")
                sys.exit(1)
            selected.append(fabric_item)

    return [
        {
            "ocid": fabric_item[0].id,
            "available": _memory_fabric_available_count(fabric_item),
            "memory_clusters": fabric_item[2],
            "fabric": fabric_item[0],
            "compute_hpc_island_id": getattr(fabric_item[0], "compute_hpc_island_id", None),
            "available_by_shape": (
                dict(fabric_item[4])
                if len(fabric_item) > 4 and isinstance(fabric_item[4], dict)
                else {}
            ),
        }
        for fabric_item in selected
    ]

def set_memory_fabric_recycle_level(fabric_id, recycle_level):
    if recycle_level is None:
        return
    if recycle_level not in ("SKIP_RECYCLE", "FULL_RECYCLE"):
        logger.error(f"Invalid GPU memory fabric recycle level: {recycle_level}")
        sys.exit(1)

    fabric_response = CLIENTS.compute_client.get_compute_gpu_memory_fabric(fabric_id)
    fabric = fabric_response.data
    preferences = getattr(fabric, "memory_fabric_preferences", None)
    if isinstance(preferences, dict):
        customer_desired_firmware_bundle_id = (
            preferences.get("customerDesiredFirmwareBundleId")
            or preferences.get("customer_desired_firmware_bundle_id")
        )
    else:
        customer_desired_firmware_bundle_id = getattr(preferences, "customer_desired_firmware_bundle_id", None)

    memory_fabric_preferences = {"fabricRecycleLevel": recycle_level}
    if customer_desired_firmware_bundle_id:
        memory_fabric_preferences["customerDesiredFirmwareBundleId"] = customer_desired_firmware_bundle_id
        logger.info(
            f"Preserving customer desired firmware bundle {customer_desired_firmware_bundle_id} "
            f"for GPU memory fabric {fabric_id}"
        )

    logger.info(f"Setting GPU memory fabric {fabric_id} recycle level to {recycle_level}")
    CLIENTS.compute_client.update_compute_gpu_memory_fabric(
        fabric_id,
        {"memoryFabricPreferences": memory_fabric_preferences},
    )

def delete_memory_cluster(memory_cluster_id,nodelist,recycle_level=None):
    try:
        memory_cluster=CLIENTS.compute_client.get_compute_gpu_memory_cluster(memory_cluster_id).data
    except oci.exceptions.ServiceError as e:
        if e.status == 404:
            logger.warning(f"Skipping memory cluster {memory_cluster_id}: it cannot be found or is not authorized")
            return None
        else:
            logger.error(f"Error reading memory cluster {memory_cluster_id}: {e}")
        sys.exit(1)
    if memory_cluster is None:
        logger.warning(f"Skipping memory cluster {memory_cluster_id}: it cannot be found")
        return None
    mc_id=memory_cluster.id
    cluster_data=CLIENTS.compute_client.get_compute_gpu_memory_cluster(mc_id).data
    cluster_ocid=cluster_data.compute_cluster_id
    if recycle_level:
        set_memory_fabric_recycle_level(cluster_data.gpu_memory_fabric_id, recycle_level)
    instance_summaries = CLIENTS.compute_client.list_compute_gpu_memory_cluster_instances(mc_id).data.items
    node_ocids = {
        node.ocid
        for node in nodelist
        if getattr(node, "ocid", None)
    }
    instance_ocids = {
        instance_summary.id
        for instance_summary in instance_summaries
        if getattr(instance_summary, "id", None)
    }
    if instance_ocids and not node_ocids:
        logger.warning(
            "Deleting compute GPU memory cluster %s with %s OCI instance(s) and no matching mgmt DB nodes",
            cluster_data.display_name or mc_id,
            len(instance_ocids),
        )
    elif instance_ocids and node_ocids and not (instance_ocids & node_ocids):
        logger.warning(
            "Deleting compute GPU memory cluster %s even though mgmt DB nodes do not match OCI instances",
            cluster_data.display_name or mc_id,
        )
    logger.info(f"Deleting compute GPU memory cluster {cluster_data.display_name or mc_id} ({mc_id})")
    CLIENTS.compute_client.delete_compute_gpu_memory_cluster(mc_id)
    return cluster_ocid


def delete_compute_cluster(cluster_ocid):
    cluster_name=CLIENTS.compute_client.get_compute_cluster(cluster_ocid).data.display_name
    CLIENTS.compute_client.delete_compute_cluster(cluster_ocid)
    remove_inventory(cluster_name)


def get_instance_network_info(instance_ocid, compartment_ocid):
    """
    Fetch instance primary private IP and subnet CIDR dynamically.
    inputs:
        instance_ocid: Instance OCID from event paylod, type=string
        compartment_ocid: Compartment OCID from event paylod (same as var.targetCompartment in terraform), type=string
    outputs:
        (private_ip, subnet_cidr)
    """

    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()

    core_client = oci.core.ComputeClient(config={}, signer=signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
    virtual_network_client = oci.core.VirtualNetworkClient(config={}, signer=signer, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)

    vnic_attachments = oci.pagination.list_call_get_all_results(
        core_client.list_vnic_attachments,
        compartment_id=compartment_ocid,
        instance_id=instance_ocid
    ).data

    if not vnic_attachments:
        raise RuntimeError(f"No VNIC attachments found for instance {instance_ocid}")

    # pick primary if present, else first
    primary_attachment = next((va for va in vnic_attachments if getattr(va, "is_primary", False)), vnic_attachments[0])

    vnic = virtual_network_client.get_vnic(primary_attachment.vnic_id).data
    subnet = virtual_network_client.get_subnet(vnic.subnet_id).data

    private_ip = vnic.private_ip
    subnet_cidr = subnet.cidr_block

    return private_ip, subnet_cidr


def update_dns(instance_ocid, zone_name, compartment_ocid, instance_launch, hostname, vcn_compartment, instance_ip=None, hostname_convention=None):
    """
    Update DNS for instance launching and instance terminating
    inputs:
        instance_ocid: Instance OCID from event paylod, type=string
        zone_name: <cluster_name>.local coming from Terraform, type=string
        compartment_ocid: Compartment OCID from event payload (same as var.targetCompartment in terraform), type=string
        instance_launch: launching or terminating instance type=boolean
        hostname: current instance name from OCI web console, type=string
        vcn_compartment: Compartment OCID for vcn (same as var.vcn_compartment in terraform), type=string
        instance_ip: private IP of the instance, type=string, optional
    output:
        hostname: new display name in web console hostname_convention+"-"+str(index), type=string if updated or corresponds to hostname if not
        private_ip: private IP if instance is launch type=string, None otherwise
    """
    zone_id = CLIENTS.dns_client.list_zones(
        compartment_id=vcn_compartment,
        name=zone_name,
        zone_type="PRIMARY",
        scope="PRIVATE"
    ).data[0].id
    if instance_launch:
        if instance_ip is None:
            private_ip, runtime_subnet = get_instance_network_info(instance_ocid, compartment_ocid)
        else:
            private_ip=instance_ip
            runtime_subnet=None
        if hostname is None:
            if runtime_subnet is None:
                raise ValueError("runtime_subnet is required when hostname is not provided")
            if hostname_convention is None:
                raise ValueError("hostname_convention is required when hostname is not provided")
            runtime_subnet_cidr = ipaddress.ip_network(runtime_subnet, strict=False)
            index = list(runtime_subnet_cidr.hosts()).index(private_ip)+2
            hostname = hostname_convention+"-"+str(index)
        CLIENTS.dns_client.update_rr_set(zone_name_or_id=zone_id,domain=hostname+"."+zone_name,rtype="A",update_rr_set_details=oci.dns.models.UpdateRRSetDetails(items=[oci.dns.models.RecordDetails(domain=hostname+"."+zone_name,rdata=private_ip,rtype="A",ttl=3600,)]))
        logger.info(f"DNS updated for instance launch with IP {private_ip} and {hostname}")
    else:
        CLIENTS.dns_client.delete_rr_set(zone_name_or_id=zone_id,domain=hostname+"."+zone_name,rtype="A")
        logger.info(f"DNS updated for instance terminated with hostname: {hostname}")



def update_display_name(instance_ocid, new_hostname):
    """
    Update display name in OCI web console to match hostname convention
    inputs:
        instance_ocid: Instance OCID from event paylod, type=string
        new_hostname: new display name in web console hostname_convention+"-"+str(index), type=string
    outputs:
        None
    """

    max_retries = 30
    retries = 0
    # adding a while loop because retry_strategy doesn't work as expected. Check the state and make sure it's RUNNING before changing hostname
    while CLIENTS.compute_client.get_instance(instance_ocid).data.display_name != new_hostname and retries <= max_retries:
        if CLIENTS.compute_client.get_instance(instance_ocid).data.lifecycle_state != "RUNNING":
            time.sleep(2*(1+retries))
            retries +=1
        else:
            # define a retry strategy
            retry_strategy_via_constructor = oci.retry.RetryStrategyBuilder(
                # Make up to 20 service calls
                max_attempts_check=True,
                max_attempts=20,

                # Don't exceed a total of 300 seconds for all service calls
                total_elapsed_time_check=True,
                total_elapsed_time_seconds=300,

                # Wait 10 seconds between attempts
                retry_max_wait_between_calls_seconds=10,

                # Use 2 seconds as the base number for doing sleep time calculations
                retry_base_sleep_time_seconds=2,

                # Retry on certain service errors:
                #
                #   - 5xx code received for the request
                #   - 409s and 429
                service_error_check=True,
                service_error_retry_on_any_5xx=True,
                service_error_retry_config={
                    409: [],
                    429: []
                },

                # Use exponential backoff and retry with full jitter, but on throttles use
                # exponential backoff and retry with equal jitter
                backoff_type=oci.retry.BACKOFF_FULL_JITTER_EQUAL_ON_THROTTLE_VALUE
            ).get_retry_strategy()
            update_instance_response = CLIENTS.compute_client.update_instance(
                instance_id=instance_ocid,
                update_instance_details=oci.core.models.UpdateInstanceDetails(display_name=new_hostname),
                retry_strategy=retry_strategy_via_constructor)
            logger.info(f"Display name updated: {new_hostname} for instance launch with OCID: {instance_ocid}")
    return
