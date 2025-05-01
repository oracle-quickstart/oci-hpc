import json
import oci
from mgmt_shared_logging import logger
import mgmt_utils

HTTP_SERVER_PORT=9876

class Node:
    def __init__(self, data, oci_clients):
        self.__dict__.update(data)
        self.instance_type=None
        self.clustertype=None
        self.cluster_ocid=None
        self.computeClient=oci_clients["computeClient"]
        self.ComputeClientCompositeOperations=oci_clients["ComputeClientCompositeOperations"]
        self.computeManagementClient=oci_clients["computeManagementClient"]
        self.ComputeManagementClientCompositeOperations=oci_clients["ComputeManagementClientCompositeOperations"]
        self.virtualNetworkClient=oci_clients["virtualNetworkClient"]
        self.DNSClient=oci_clients["DNSClient"]
        self.IdentityClient=oci_clients["IdentityClient"]
        self.IdentityClientCompositeOperations=oci_clients["IdentityClientCompositeOperations"]
    
    def tag_unhealthy(self):
        instance = self.computeClient.get_instance(instance_id=self.ocid).data
        tags = instance.defined_tags
        tags.update({'ComputeInstanceHostActions': { 'CustomerReportedHostStatus': 'unhealthy' }})
        update_instance_details = oci.core.models.UpdateInstanceDetails(defined_tags=tags)
        logger.info("Updating tags on instance: "+self.hostname+" with OCID:"+self.ocid)
        try:
            update_instance_response = self.ComputeClientCompositeOperations.update_instance_and_wait_for_state(self.ocid, update_instance_details,wait_for_states=["RUNNING"])
        except oci.exceptions.ServiceError as e:
            logger.error("The tag does not exists or the controller doesn't have acces to the tag")
            logger.error("Make sure the Tag namespace ComputeInstanceHostActions exists with the defined tag: CustomerReportedHostStatus")

    def terminate(self):
        if self.clustertype is None:
            self.get_instance_type()
        try:
            if self.clustertype == "SA" or self.clustertype == "CC":
                logger.info("Terminating node with details "+self.hostname+", "+self.oci_name+", "+self.ip_address)
                self.ComputeClientCompositeOperations.terminate_instance_and_wait_for_state(self.cluster_ocid,wait_for_states=["TERMINATING","TERMINATED"])
            elif self.clustertype == "IPA" or self.clustertype == "CN":
                logger.info("Terminating node with details "+self.hostname+", "+self.oci_name+", "+self.ip_address)
                instance_details = oci.core.models.DetachInstancePoolInstanceDetails(instance_id=self.ocid,is_auto_terminate=True,is_decrement_size=True)
                self.ComputeManagementClientCompositeOperations.detach_instance_pool_instance_and_wait_for_work_request(self.cluster_ocid,instance_details)
        except oci.exceptions.ServiceError as e:
            logger.error(f"Error: {e}")

    def reboot(self):
        if self.ocid == "None":
            for instance in oci.pagination.list_call_get_all_results(self.computeClient.list_instances(compartment_id=self.compartment)).data:
                for potential_vnic_attachment in oci.pagination.list_call_get_all_results(self.computeClient.list_vnic_attachments,compartment_id=self.compartment,instance_id=instance.id).data:
                    if potential_vnic_attachment.display_name is None:
                        try:
                            vnic_attachment = potential_vnic_attachment
                            vnic = self.virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                            if vnic.private_ip == self.ip_address:
                                self.ocid=instance.id
                        except:
                            continue
        logger.info("Rebooting: "+self.hostname+" with oci name "+self.oci_name+" with IP "+self.ip_address+" and OCID:"+self.ocid)
        self.computeClient.instance_action(instance_id=self.ocid,action="RESET")

    def bvr(self,image_ocid):
        update_instance_source_details = oci.core.models.UpdateInstanceSourceViaImageDetails()
        update_instance_source_details.image_id = image_ocid
        update_instance_source_details.is_preserve_boot_volume_enabled = False
        update_instance_source_details.is_force_stop_enabled = True
        update_instance_details = oci.core.models.UpdateInstanceDetails()
        update_instance_details.source_details = update_instance_source_details
        self.ComputeClientCompositeOperations.update_instance_and_wait_for_state(self.ocid, update_instance_details,wait_for_states=["STOPPING","STOPPED","STARTING","RUNNING"])

    def get_instance_type(self):
        if self.clustertype is None:
            instance_pools = oci.pagination.list_call_get_all_results(self.computeManagementClient.list_cluster_networks,self.compartment,display_name=self.cluster_name).data
            if len(instance_pools):
                for instance_pool in instance_pools:
                    ipa_ocid=instance_pool.instance_pools[0].id
                    instance_summaries = oci.pagination.list_call_get_all_results(self.computeManagementClient.list_instance_pool_instances,self.compartment,ipa_ocid).data
                    for instance_summary in instance_summaries:
                        if instance_summary.id == self.ocid:
                            self.clustertype="CN"
                            self.cluster_ocid=ipa_ocid
                            return self.clustertype,self.cluster_ocid

            instance_pools = oci.pagination.list_call_get_all_results(self.computeManagementClient.list_instance_pools,self.compartment,display_name=self.cluster_name).data
            if len(instance_pools):
                for instance_pool in instance_pools:
                    instance_summaries = oci.pagination.list_call_get_all_results(self.computeManagementClient.list_instance_pool_instances,self.compartment,instance_pool.id).data
                    for instance_summary in instance_summaries:
                        if instance_summary.id == self.ocid:
                            self.clustertype="IPA"
                            self.cluster_ocid=instance_pool.id
                            return self.clustertype,self.cluster_ocid
            try:
                instance_pools = self.computeClient.list_compute_clusters(self.compartment,display_name=self.cluster_name).data.items
            except:
                logger.warning(f"Compute clusters are not enabled in this region")
                instance_pools = []
            if len(instance_pools):
                for instance_pool in instance_pools:
                    instance_summaries = self.computeClient.list_instances(self.compartment,compute_cluster_id=instance_pool.id).data
                    for instance_summary in instance_summaries:
                        if instance_summary.id == self.ocid:
                            self.clustertype="CC"
                            self.cluster_ocid=instance_pool.id
                            return self.clustertype,self.cluster_ocid
            instance_summaries = self.computeClient.list_instances(compartment_id=self.compartment).data
            for instance_summary in instance_summaries:
                if instance_summary.id == self.ocid:
                    self.clustertype="SA"
                    self.cluster_ocid=None
                    return self.clustertype,self.cluster_ocid
        else:
            return self.clustertype,self.cluster_ocid

    def grab_http_content(self):
        url=f"http://{self.ip_address}:{HTTP_SERVER_PORT}/info"

    def reconfigure_controller(self):
        mgmt_utils.reconfigure_controller(self.ocid)   
    def print_dict(self):
        print(json.dumps(self.__dict__, indent=4, default=str).replace("\\n", "\n"))