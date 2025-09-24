import os
import oci
import logging
import io
import json
import ipaddress
import time
from fdk import response

queue_ocid = os.environ["QUEUE_OCID"]
controller_name = os.environ["CONTROLLER_NAME"]
private_subnet= os.environ["PRIVATE_SUBNET"]
cluster_name = os.environ["CLUSTER_NAME"]
zone_name = cluster_name+".local"

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




def get_tag_controller(instance_ocid, controller_name):
    """
    Check if instance has the right tag for controller and get hostname_convention via instance tag
    inputs:
        instance_ocid: Instance OCID from event paylod, type=string
        controller_name: controller name with <cluster_name>-controller coming from Terraform, type=string
    outputs:
        boolean: has the right controller tag or not 
        hostname_convention: hostname convention according to freeform tags, type=string or None
        hostname: instance hostname, type=string    or None if not matching
        defined_hostname: New hostname to be set, type=string    or None if not matching
    """
    signer = oci.auth.signers.get_resource_principals_signer() # Resource principal
    #signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    core_client = oci.core.ComputeClient(config={}, signer=signer)

    get_instance_response = core_client.get_instance(
        instance_id=instance_ocid)
    if get_instance_response.data.freeform_tags and "controller_name" in get_instance_response.data.freeform_tags and get_instance_response.data.freeform_tags["controller_name"] == controller_name:
        if "hostname_convention" in get_instance_response.data.freeform_tags and get_instance_response.data.freeform_tags["hostname_convention"].title().strip() != "None":
            hostname_convention = get_instance_response.data.freeform_tags["hostname_convention"]
        else: 
            hostname_convention = None
        if "defined_hostname" in get_instance_response.data.freeform_tags and get_instance_response.data.freeform_tags["defined_hostname"].title().strip() != "None":
            defined_hostname = get_instance_response.data.freeform_tags["defined_hostname"]
        else: 
            defined_hostname = None
        if "cluster_name" in get_instance_response.data.freeform_tags and get_instance_response.data.freeform_tags["cluster_name"].title().strip() != "None":
            cluster_name = get_instance_response.data.freeform_tags["cluster_name"]
        else: 
            cluster_name = None
        hostname = get_instance_response.data.display_name
        return True, hostname_convention, hostname, defined_hostname, cluster_name
    else:
        return False, None, None, None, None


def get_private_ip(instance_ocid,compartment_ocid):
    """
    fetch the private ip of the instance
    inputs:
        instance_ocid: Instance OCID from event paylod, type=string
        compartment_ocid: Compartment OCID from event paylod (same as var.targetCompartment in terraform), type=string
    outputs:
        private_ips_for_vnic: instance private IP, type=string
    """

    signer = oci.auth.signers.get_resource_principals_signer() # Resource principal
    #signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()

    core_client = oci.core.ComputeClient(config={}, signer=signer)
    virtual_network_client = oci.core.VirtualNetworkClient(config={}, signer=signer)

    vnic_attachments = oci.pagination.list_call_get_all_results(
        core_client.list_vnic_attachments,
        compartment_id=compartment_ocid,
        instance_id=instance_ocid
    ).data

    vnics = [virtual_network_client.get_vnic(va.vnic_id).data for va in vnic_attachments]

    private_ips_for_vnic = oci.pagination.list_call_get_all_results(
        virtual_network_client.list_private_ips,
        vnic_id=vnics[0].id
    ).data[0].ip_address
    return private_ips_for_vnic

def update_dns(private_subnet, instance_ocid, hostname_convention, zone_name, compartment_ocid, instance_launch, hostname, defined_hostname):
    """
    Update DNS for instance launching and instance terminating
    inputs: 
        private_subnet: CIDR range of private subnet, type=string
        instance_ocid: Instance OCID from event paylod, type=string
        hostname_convention: Hostname convention as indicated in the stack option, type=string
        zone_name: <cluster_name>.local coming from Terraform, type=string
        compartment_ocid: Compartment OCID from event payload (same as var.targetCompartment in terraform), type=string
        instance_launch: launching or terminating instance type=boolean
        hostname: current instance name from OCI web console, type=string
        defined_hostname: New hostname to be set, type=string    or None if not matching
    output: 
        hostname: new display name in web console hostname_convention+"-"+str(index), type=string if updated or corresponds to hostname if not
        private_ip: private IP if instance is launch type=string, None otherwise
    """
    signer = oci.auth.signers.get_resource_principals_signer() # Resource principal
    #signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()    
    dns_client = oci.dns.DnsClient(config={}, signer=signer)
    zone_id=dns_client.list_zones(compartment_id=compartment_ocid,name=zone_name,zone_type="PRIMARY",scope="PRIVATE").data[0].id
    private_ip = None
    if instance_launch:
        private_ip = get_private_ip(instance_ocid,compartment_ocid)
        if hostname_convention and not defined_hostname:
            ip = ipaddress.ip_address(private_ip)
            private_subnet_cidr=ipaddress.ip_network(private_subnet)
            index = list(private_subnet_cidr.hosts()).index(ip)+2
            convention_zone=hostname_convention+"-"+str(index)+"."+zone_name
            hostname = hostname_convention+"-"+str(index)
        if defined_hostname:
            hostname = defined_hostname

        get_rr_set_response = dns_client.update_rr_set(zone_name_or_id=zone_id,domain=hostname+"."+zone_name,rtype="A",scope="PRIVATE",update_rr_set_details=oci.dns.models.UpdateRRSetDetails(items=[oci.dns.models.RecordDetails(domain=hostname+"."+zone_name,rdata=private_ip,rtype="A",ttl=3600,)]))
        logging.getLogger().info(f"DNS updated for instance launch with IP {private_ip} and {hostname}")
    else:
        get_rr_set_response = dns_client.delete_rr_set(zone_name_or_id=zone_id,domain=hostname+"."+zone_name,rtype="A",scope="PRIVATE") 
        logging.getLogger().info(f"DNS updated for instance terminated with hostname: {hostname}")

 
    return hostname, private_ip

def update_display_name(instance_ocid, new_hostname):
    """
    Update display name in OCI web console to match hostname convention
    inputs:
        instance_ocid: Instance OCID from event paylod, type=string
        new_hostname: new display name in web console hostname_convention+"-"+str(index), type=string
    outputs:
        None
    """
    signer = oci.auth.signers.get_resource_principals_signer() # Resource principal
    #signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()

    core_client = oci.core.ComputeClient(config={}, signer=signer)

    max_retries = 30
    retries = 0
    # adding a while loop because retry_strategy doesn't work as expected. Check the state and make sure it's RUNNING before changing hostname
    while core_client.get_instance(instance_ocid).data.display_name != new_hostname and retries <= max_retries:    
        if core_client.get_instance(instance_ocid).data.lifecycle_state != "RUNNING":
            print ("not ready")
            print (retries)
            time.sleep(2*(1+retries))
            retries +=1
        else:    
            update_instance_response = core_client.update_instance(
                instance_id=instance_ocid,
                update_instance_details=oci.core.models.UpdateInstanceDetails(display_name=new_hostname),
                #retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY)
                retry_strategy=retry_strategy_via_constructor)
            logging.getLogger().info(f"Display name updated: {new_hostname} for instance launch with OCID: {instance_ocid}")    
    return   


def write_message_queue(controller_name, queue_ocid, instance_ocid, compartment_ocid, event_type, zone_name):
    """
    write message to queue with private ip and "starting" or "terminating" status
    inputs:
        controller_name: controller name with <cluster_name>-controller coming from Terraform, type=string
        queue_ocid: coming from Terraform, type=string
        instance_ocid: Instance OCID from event paylod, type=string
        compartment_ocid: Compartment OCID from event payload (same as var.targetCompartment in terraform), type=string
        event_type: type of event from event payload, type=string
        zone_name: <cluster_name>.local coming from Terraform, type=string
    outputs:
        put_messages_response.data: response from teh API call. Returns the message
    """
    # check if instance has matching controller_name tag
    is_instance, hostname_convention, hostname, defined_hostname, cluster_name = get_tag_controller(instance_ocid, controller_name)

    if not is_instance:
        return
    else:
        signer = oci.auth.signers.get_resource_principals_signer() # Resource principal
        #signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()


        if event_type == "com.oraclecloud.computeapi.launchinstance.end":
            instance_launch = True            
            new_hostname, private_ip = update_dns(private_subnet, instance_ocid, hostname_convention, zone_name, compartment_ocid, instance_launch,hostname, defined_hostname)
            if hostname_convention:    
                try:
                    update_display_name(instance_ocid, new_hostname)
                except Exception as ex:
                    logging.getLogger().error(str(ex))
                    raise  
            content_dict = {"ip_address": private_ip,"cluster_name": cluster_name,"status": "starting","ocid":instance_ocid,"hostname":new_hostname,"compartment":compartment_ocid}
        else:
            instance_launch = False
            update_dns(private_subnet, instance_ocid, hostname_convention, zone_name, compartment_ocid, instance_launch,hostname, defined_hostname)
            content_dict = {"hostname": hostname,"cluster_name": cluster_name,"status": "terminating","ocid":instance_ocid,"compartment_id":compartment_ocid}    
        content = json.dumps(content_dict, indent = 4) 
        cp_client = oci.queue.QueueAdminClient(config={}, signer=signer)
        endpoint = cp_client.get_queue(queue_ocid).data.messages_endpoint
        queue_client = oci.queue.QueueClient(config={}, signer=signer, service_endpoint=endpoint)

        put_messages_response = queue_client.put_messages(
            queue_id = queue_ocid,
            put_messages_details=oci.queue.models.PutMessagesDetails(
                messages=[
                    oci.queue.models.PutMessagesDetailsEntry(
                        content=content,
                        metadata=oci.queue.models.MessageMetadata(
                            channel_id=controller_name))]))
        return (put_messages_response.data)   

def handler(ctx, data: io.BytesIO=None):
    try:
        payload_bytes = data.getvalue()
        if payload_bytes==b'':
            raise KeyError('No keys in payload')
        payload = json.loads(payload_bytes)
        instance_ocid = payload["data"]["resourceId"]
        compartment_ocid = payload["data"]["compartmentId"]
        event_type = payload["eventType"]
    except Exception as ex:
        print('ERROR: Missing key in payload', ex, flush=True)
        raise

    resp = ""
    write_message_queue(controller_name, queue_ocid, instance_ocid, compartment_ocid, event_type, zone_name)


    return response.Response(
        ctx,
        response_data=resp,
        headers={"Content-Type": "application/json"}
    )