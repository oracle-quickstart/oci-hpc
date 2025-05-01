
from mgmt_shared_logging import logger
import oci
import time,os
import base64
import random, string, re

class Cluster:
    def __init__(self, clustername, nodeList, oci_clients):
        self.cluster_name=clustername
        self.nodeList=nodeList

        self.computeClient=oci_clients["computeClient"]
        self.ComputeClientCompositeOperations=oci_clients["ComputeClientCompositeOperations"]
        self.computeManagementClient=oci_clients["computeManagementClient"]
        self.ComputeManagementClientCompositeOperations=oci_clients["ComputeManagementClientCompositeOperations"]
        self.virtualNetworkClient=oci_clients["virtualNetworkClient"]
        self.DNSClient=oci_clients["DNSClient"]
        self.IdentityClient=oci_clients["IdentityClient"]
        self.IdentityClientCompositeOperations=oci_clients["IdentityClientCompositeOperations"]

        self.compartment=None
        self.cluster_type=None
        self.cluster_ocid=None
        self.ip_ocid=None
        self.oci_object=None
        self.instance_pool_ocid=None
        self.hostname_convention=None
        self.shape=None
        self.instances=None

    def addNodeToList(self,node):
        if not node in self.nodeList:
            self.nodeList.append(node)

    def removeNode(self,node):
        self.nodeList.remove(node) 

    def set_compartment(self):
        try:
            if self.compartment is None:
                for node in self.nodeList:
                    if not node.compartment is None:
                        self.compartment = node.compartment
                        return  node.compartment
        except:
            self.compartment = None
        return self.compartment

    def get_cluster_type(self):
        if self.nodeList:
            self.cluster_type,self.cluster_ocid=self.nodeList[0].get_instance_type()

    def add(self,add_number):
        self.get_object()
        self.get_oci_instances()
        if self.cluster_type == "CC" or self.cluster_type == "SA":
            current_size=len(self.instances)
            if current_size == 0:
                logger.error("The resize script cannot work for a compute cluster if the size is there is no node in the cluster")
            else:
                first_instance=self.computeClient.get_instance(self.instances[0]['ocid']).data
                logger.info(f"Launching {add_number} in the Compute Cluster")
                for i in range(add_number):
                    if self.cluster_type == "CC":
                        launch_instance_details=self.getLaunchInstanceDetailsFromInstance(first_instance,self.cluster_ocid)
                    else:
                        launch_instance_details=self.getLaunchInstanceDetailsFromInstance(first_instance,None)
                    self.ComputeClientCompositeOperations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
        else:
            current_size=len(self.instances)
            size = current_size + add_number
            update_size = oci.core.models.UpdateInstancePoolDetails(size=size)
            logger.info(f"Launching {add_number} in the Cluster for a total size of {size}")
            self.ComputeManagementClientCompositeOperations.update_instance_pool_and_wait_for_state(self.instance_pool_ocid,update_size,['RUNNING'],waiter_kwargs={'max_wait_seconds':3600})
        self.get_oci_instances()
        newsize=len(self.instances)
        if newsize == current_size:
            logger.error("No node was added, please check the work requests of the Cluster Network and Instance Pool to see why")
            exit(1)

    def get_hostname_convention_and_shape(self,instance_config_ocid=None,instance_type=None):
        if instance_config_ocid is None:
            if not instance_type is None:
                self.hostname_convention=instance_type['hostname_convention']
                self.shape=instance_type['shape']
        else:
            instance_config=self.computeManagementClient.get_instance_configuration(instance_config_ocid)
            self.hostname_convention=instance_config.data.instance_details.launch_details.freeform_tags["hostname_convention"]
            self.shape=instance_config.instance_details.launch_details.shape

    def create(self,cluster_type,instance_type,instance_config_ocid,count,compartment_ocid,availability_domain,subnet_id,controller_hostname):
        self.get_object()
        self.get_oci_instances()
        self.cluster_type = cluster_type
        self.get_hostname_convention_and_shape(instance_config_ocid=instance_config_ocid,instance_type=instance_type)
        self.generate_inventory()
#        try:
        if instance_config_ocid is None and ( self.cluster_type == "CN"  or self.cluster_type == "IP" or self.cluster_type == "IPA" ) :
            instance_config_data=self.generate_instance_config(self,instance_type,controller_hostname)
            instance_config_ocid=instance_config_data.id
        if self.cluster_type == "CN":
            ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=subnet_id)
            ip_placement_details=oci.core.models.ClusterNetworkPlacementConfigurationDetails(availability_domain=availability_domain,primary_vnic_subnets=ip_placement_subnet_details)
            instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails(display_name=self.cluster_name,instance_configuration_id=instance_config_ocid,size=count)
            cn_details=oci.core.models.CreateClusterNetworkDetails(compartment_id=compartment_ocid,display_name=self.cluster_name,instance_pools=[instance_pools_details],placement_configuration=ip_placement_details)
            cn = self.ComputeManagementClientCompositeOperations.create_cluster_network_and_wait_for_state(create_cluster_network_details=cn_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})
            return cn.data
        elif self.cluster_type == "IP" or self.cluster_type == "IPA":
            ip_placement_subnet_details=oci.core.models.InstancePoolPlacementPrimarySubnet(subnet_id=subnet_id)
            ip_placement_details=oci.core.models.CreateInstancePoolPlacementConfigurationDetails(availability_domain=availability_domain,primary_vnic_subnets=ip_placement_subnet_details)
            instance_pools_details=oci.core.models.CreateClusterNetworkInstancePoolDetails()
            ip_details=oci.core.models.CreateInstancePoolDetails(compartment_id=compartment_ocid,display_name=self.cluster_name,placement_configurations=[ip_placement_details],instance_configuration_id=instance_config_ocid,size=count)
            cn = self.ComputeManagementClientCompositeOperations.create_instance_pool_and_wait_for_state(create_instance_pool_details=ip_details,wait_for_states=["RUNNING"],waiter_kwargs={'max_wait_seconds':3600})
            return cn.data
        elif self.cluster_type == "CC" or self.cluster_type == "SA" :
            if self.cluster_type == "CC":
                cc_details=oci.core.models.CreateComputeClusterDetails(compartment_id=compartment_ocid,availability_domain=availability_domain,display_name=self.cluster_name)
                cn = self.computeClient.create_compute_cluster(create_compute_cluster_details=cc_details).data
                cn_id=cn.id
            else:
                cn_id=None
            for i in range(count):
                if instance_type is None:
                    launch_instance_details = self.getLaunchInstanceDetailsFromInstanceConfig(instance_config_ocid,compartment_ocid,cn_id,availability_domain,subnet_id,controller_hostname)
                else:
                    launch_instance_details = self.getLaunchInstanceDetailsFromInstanceType(instance_type,subnet_id,controller_hostname,cn_id)
                self.ComputeClientCompositeOperations.launch_instance_and_wait_for_state(launch_instance_details,wait_for_states=["RUNNING"])
        #except:
        #    self.remove_inventory()
        self.get_oci_instances()

    def generate_inventory(self):
        #def generate_inventory(instance_config_details,cluster_type):
        original_inventory="/config/playbooks/inventory"
        inventory_name=f"/config/playbooks/inventory_{self.cluster_name}"
        modifications={"cluster_name":self.cluster_name,
                    "shape":self.shape,
                    "rdma_enabled":"true" if self.cluster_type in ["CN","CC"] else "false",
                    "hostname_convention": self.hostname_convention
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
    
    def remove_inventory(self):
        inventory_name=f"/config/playbooks/inventory_{self.cluster_name}"
        if os.path.exists(inventory_name):
            os.remove(inventory_name)
            logger.info(f"Inventory {inventory_name} deleted successfully.")
        else:
            logger.warning(f"Inventory {inventory_name} was not present.")

    def get_object(self):
        self.set_compartment()
        self.get_cluster_type()
        if not self.cluster_type is None:
            if self.cluster_type == "CN":
                self.oci_object= self.computeManagementClient.get_cluster_network(self.cluster_ocid)
                self.instance_pool_ocid=self.oci_object.instance_pools[0].id

            if self.cluster_type == "IPA":
                self.oci_object= self.computeManagementClient.get_instance_pool(self.cluster_ocid)
                self.instance_pool_ocid=self.oci_object.id

            if self.cluster_type == "CC":
                self.oci_object= self.computeClient.get_compute_cluster(self.cluster_ocid)

            if self.cluster_type == "SA":
                self.oci_object= None

    def get_oci_instances(self):
        cn_instances=[]
        if not self.cluster_type is None:    
            if self.cluster_type == "CC":
                instances = self.computeClient.list_instances(compartment_id=self.compartment,compute_cluster_id=self.cluster_ocid,sort_by="TIMECREATED").data
                for instance in instances:
                    if instance.lifecycle_state == "TERMINATED":
                        continue
                    try:
                        for potential_vnic_attachment in oci.pagination.list_call_get_all_results(self.computeClient.list_vnic_attachments,compartment_id=self.compartment,instance_id=instance.id).data:
                            if potential_vnic_attachment.display_name is None:
                                vnic_attachment = potential_vnic_attachment
                        vnic = self.virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                    except:
                        continue
                    cn_instances.append({'display_name':instance.display_name,'ip':vnic.private_ip,'ocid':instance.id})
            elif self.cluster_type == "SA":
                instances = self.computeClient.list_instances(compartment_id=self.compartment,sort_by="TIMECREATED").data
                for instance in instances:
                    if instance.lifecycle_state == "TERMINATED":
                        continue
                    elif len(instance.freeform_tags) == 0:
                        continue
                    elif "cluster_name" in instance.freeform_tags.keys():
                        if instance.freeform_tags["cluster_name"]!=self.cluster_name:
                            continue
                    try:
                        for potential_vnic_attachment in oci.pagination.list_call_get_all_results(self.computeClient.list_vnic_attachments,compartment_id=self.compartment,instance_id=instance.id).data:
                            if potential_vnic_attachment.display_name is None:
                                vnic_attachment = potential_vnic_attachment
                        vnic = self.virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                    except:
                        continue
                    cn_instances.append({'display_name':instance.display_name,'ip':vnic.private_ip,'ocid':instance.id})
            else:
                if self.cluster_type == "CN":
                    instance_summaries = oci.pagination.list_call_get_all_results(self.computeManagementClient.list_cluster_network_instances,self.compartment,self.cluster_ocid,sort_by="TIMECREATED").data
                elif self.cluster_type == "IPA":
                    instance_summaries = oci.pagination.list_call_get_all_results(self.computeManagementClient.list_instance_pool_instances,self.compartment,self.cluster_ocid,sort_by="TIMECREATED").data
                
                for instance_summary in instance_summaries:
                    try:
                        instance=self.computeClient.get_instance(instance_summary.id).data
                        for potential_vnic_attachment in oci.pagination.list_call_get_all_results(self.computeClient.list_vnic_attachments,compartment_id=self.compartment,instance_id=instance.id).data:
                            if potential_vnic_attachment.display_name is None:
                                vnic_attachment = potential_vnic_attachment
                        vnic = self.virtualNetworkClient.get_vnic(vnic_attachment.vnic_id).data
                    except:
                        continue
                    cn_instances.append({'display_name':instance_summary.display_name,'ip':vnic.private_ip,'ocid':instance_summary.id})
        self.instances=cn_instances

    def delete_cluster(self):
        self.get_object()
        if self.cluster_type == "CN":
            self.computeManagementClient.terminate_cluster_network(self.cluster_ocid)
        elif self.cluster_type == "IPA":
            self.computeManagementClient.terminate_instance_pool(self.cluster_ocid)
        elif self.cluster_type == "CC" or self.cluster_type == "SA":
            self.get_oci_instances()
            for instance in self.instances:
                self.ComputeClientCompositeOperations.terminate_instance_and_wait_for_state(instance['ocid'],wait_for_states=["TERMINATING","TERMINATED"])
            instance_running=True
            while instance_running:
                instance_running=False
                for instance in self.instances:
                    if self.computeClient.get_instance(instance['ocid']).data.lifecycle_state != "TERMINATED":
                        instance_running=True
                        time.sleep(30)
            if self.cluster_type == "CC":
                self.computeClient.delete_compute_cluster(self.cluster_ocid)
        self.remove_inventory()
    
    def print_nodes(self):
        for i in self.nodeList:
            i.print_dict()

    def generate_instance_config(self,instance_type,controller_hostname):
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
        RDMA=instance_type['rdma_enabled']
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
            new_tags={"cluster_name" : self.cluster_name, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}

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
                display_name= self.cluster_name,
                instance_details=new_instance_details
            )

            create_response = self.computeManagementClient.create_instance_configuration(new_config_details).data
            # Check that the instance config can be queried.
            for i in range(10):
                try:
                    create_response=self.computeManagementClient.get_instance_configuration(create_response.id).data
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

    def getLaunchInstanceDetailsFromInstanceConfig(self,instance_config_ocid,compartment_ocid,cn_ocid,availability_domain,subnet_id,controller_hostname):
        instance_config=self.computeManagementClient.get_instance_configuration(instance_config_ocid).data
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
        new_tags["cluster_name"] = self.cluster_name
        if not 'controller_name' in new_tags.keys():
            new_tags['controller_name'] = controller_hostname

        defined_tags=instance_config.instance_details.launch_details.defined_tags

        new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+self.cluster_name
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

    def getLaunchInstanceDetailsFromInstanceType(self,instance_type,subnet_id,controller_hostname,cn_ocid):

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
        RDMA=instance_type['rdma_enabled']
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
            new_tags={"cluster_name" : self.cluster_name, "controller_name" : controller_hostname, "hostname_convention" : hostname_convention}

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
                compute_cluster_id=cn_ocid
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
                compute_cluster_id=cn_ocid
                ) 
            return new_launch_details
        except oci.exceptions.ServiceError as e:
            logger.error(f"An error occurred: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
        
    def getLaunchInstanceDetailsFromInstance(self,instance,cn_ocid):

        agent_config=instance.agent_config
        agent_config.__class__ = oci.core.models.LaunchInstanceAgentConfigDetails

        for potential_vnic_attachment in oci.pagination.list_call_get_all_results(self.computeClient.list_vnic_attachments,compartment_id=self.compartment,instance_id=instance.id).data:
            if potential_vnic_attachment.display_name is None:
                vnic_attachment = potential_vnic_attachment
        create_vnic_details=oci.core.models.CreateVnicDetails(assign_public_ip=False,subnet_id=vnic_attachment.subnet_id)

        shape_config=instance.shape_config
        try:
            nvmes=shape_config.local_disks
            if not nvmes:
                raise ValueError("No NVMEs")
            launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,nvmes=nvmes,ocpus=shape_config.ocpus)
        except:
            launchInstanceShapeConfigDetails = oci.core.models.LaunchInstanceShapeConfigDetails(baseline_ocpu_utilization=shape_config.baseline_ocpu_utilization,memory_in_gbs=shape_config.memory_in_gbs,ocpus=shape_config.ocpus)
        new_display_name = "inst-"+''.join(random.choices(string.ascii_lowercase, k=5))+"-"+self.cluster_name
        if instance.shape.startswith("BM"):
            launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=instance.availability_domain, compartment_id=self.compartment,compute_cluster_id=cn_ocid,shape=instance.shape,source_details=instance.source_details,metadata=instance.metadata,display_name=new_display_name,freeform_tags=instance.freeform_tags,create_vnic_details=create_vnic_details)
        else:
            launch_instance_details=oci.core.models.LaunchInstanceDetails(agent_config=agent_config,availability_domain=instance.availability_domain, compartment_id=self.compartment,compute_cluster_id=cn_ocid,shape=instance.shape,shape_config=launchInstanceShapeConfigDetails,source_details=instance.source_details,metadata=instance.metadata,display_name=new_display_name,freeform_tags=instance.freeform_tags,create_vnic_details=create_vnic_details)
        return launch_instance_details