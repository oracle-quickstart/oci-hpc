import oci
import oci.core
import oci.util
import argparse

def list_instance_configurations(compartment_id, compute_mgmt_client):
    """
    Lists available instance configurations in the compartment and lets the user choose one.
    Returns the selected instance configuration object.
    """
    response = oci.pagination.list_call_get_all_results(compute_mgmt_client.list_instance_configurations,compartment_id)
    instance_configs = response.data
    if not instance_configs:
        print("No instance configurations found.")
        return None
    print("\nAvailable Instance Configurations:")
    for idx, config in enumerate(instance_configs, 1):
        print(f"{idx}. {config.display_name} ({config.id})")
    choice = int(input("\nEnter the number of the instance config to use: ")) - 1
    return instance_configs[choice] if 0 <= choice < len(instance_configs) else None

def get_instance_config_details(instance_config_id, compute_mgmt_client):
    """Retrieves details of an instance configuration."""
    response = compute_mgmt_client.get_instance_configuration(instance_config_id)
    return response.data

def list_cluster_networks(compartment_id, compute_mgmt_client):
    """
    Lists available cluster networks in the compartment and lets the user choose one.
    Returns the selected cluster network object.
    """
    response = oci.pagination.list_call_get_all_results(compute_mgmt_client.list_cluster_networks, compartment_id)
    cluster_networks = response.data
    cluster_networks_instance_pools = {}
    for cn in cluster_networks:
        cluster_networks_instance_pools[cn.id] = []
        instance_pools = compute_mgmt_client.get_cluster_network(cn.id).data.instance_pools
        for instance_pool in instance_pools:
            instance_pool_config = compute_mgmt_client.get_instance_pool(instance_pool.id).data
            cluster_networks_instance_pools[cn.id].append(instance_pool_config)
    return cluster_networks, cluster_networks_instance_pools


def list_compute_gpu_memory_clusters(compartment_id, compute_client):
    """
    Lists available gpu memory clusters in the compartment and lets the user .
    Returns the selected cluster network object.
    """
    response = compute_client.list_compute_gpu_memory_clusters(compartment_id=compartment_id)
    gpu_memory_clusters = response.data
    gmcs = []
    for entry in gpu_memory_clusters.items:
        gmc = compute_client.get_compute_gpu_memory_cluster(entry.id)
        gmcs.append(gmc.data)
    return gmcs

# ------------------------------
# Core Function: Full Replication with SSH Key Replacement
# ------------------------------

def create_instance_configuration_from_details(compartment_id, src_config, new_ssh_key, new_bv_size, new_image_id, new_cloud_init, new_instance_config_name):
    """
    Creates a new instance configuration by fully replicating the source configuration.
    If a new SSH key is provided, it replaces the SSH key in the launch metadata.
    """
    try:
        launch = src_config.instance_details.launch_details
        # Update metadata with new SSH key; create a copy if it exists.
        new_metadata = dict(launch.metadata) if launch.metadata else {}
        if new_ssh_key:
            new_metadata["ssh_authorized_keys"] = new_ssh_key
        if new_cloud_init:
            new_metadata["user_data"] = oci.util.file_content_as_launch_instance_user_data(new_cloud_init)

        # Build Agent Config if present
        new_agent_config = None
        if launch.agent_config:
            new_agent_config = oci.core.models.InstanceConfigurationLaunchInstanceAgentConfigDetails(
                are_all_plugins_disabled=launch.agent_config.are_all_plugins_disabled,
                is_management_disabled=launch.agent_config.is_management_disabled,
                is_monitoring_disabled=launch.agent_config.is_monitoring_disabled,
                plugins_config=[
                    oci.core.models.InstanceAgentPluginConfigDetails(
                        desired_state=plugin.desired_state,
                        name=plugin.name
                    ) for plugin in (launch.agent_config.plugins_config or [])
                ]
            )

        # Build Create VNIC Details if present
        new_create_vnic = None
        if launch.create_vnic_details:
            new_create_vnic = oci.core.models.InstanceConfigurationCreateVnicDetails(
                assign_public_ip=launch.create_vnic_details.assign_public_ip,
                assign_private_dns_record=launch.create_vnic_details.assign_private_dns_record,
                subnet_id=launch.create_vnic_details.subnet_id,
                nsg_ids=launch.create_vnic_details.nsg_ids,
                assign_ipv6_ip=launch.create_vnic_details.assign_ipv6_ip
                # Additional fields can be added here if needed
            )

        # Build Source Details
        src_details = launch.source_details
        if new_bv_size:
            bv_size=new_bv_size
        else:
            bv_size=getattr(src_details, 'boot_volume_size_in_gbs', None)
        if new_image_id:
            image_id=new_image_id
        else:
            image_id=src_details.image_id
        if new_instance_config_name:
            instance_config_name=new_instance_config_name
        else:
            instance_config_name=src_config.display_name + "-copy"

        new_source_details = oci.core.models.InstanceConfigurationInstanceSourceViaImageDetails(
            source_type=src_details.source_type,
            image_id=image_id,
            boot_volume_size_in_gbs=bv_size,
            boot_volume_vpus_per_gb=getattr(src_details, 'boot_volume_vpus_per_gb', None)
        )

        # Build new Launch Details copying as many fields as possible
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
            is_pv_encryption_in_transit_enabled=launch.is_pv_encryption_in_transit_enabled
        )

        # Build new Instance Details
        new_instance_details = oci.core.models.ComputeInstanceDetails(
            instance_type=src_config.instance_details.instance_type,
            launch_details=new_launch_details,
            block_volumes=src_config.instance_details.block_volumes,
            secondary_vnics=src_config.instance_details.secondary_vnics
        )

        # Construct new Instance Configuration Details object
        new_config_details = oci.core.models.CreateInstanceConfigurationDetails(
            compartment_id=src_config.compartment_id,
            display_name=instance_config_name,
            instance_details=new_instance_details,
            defined_tags=src_config.defined_tags,
            freeform_tags=src_config.freeform_tags
        )

        # Create the new instance configuration using the Compute Management Client
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        compute_mgmt_client = oci.core.ComputeManagementClient(config={}, signer=signer)
        response = compute_mgmt_client.create_instance_configuration(new_config_details)
        return response.data

    except oci.exceptions.ServiceError as e:
        print(f"An error occurred: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

# ------------------------------
# Attach Instance Config to Cluster Network
# ------------------------------

def attach_instance_config_to_cluster_network(cluster_network_id, instance_pool_ids, new_instance_config_id, compute_mgmt_client):
    for instance_pool_id in instance_pool_ids:
        try:
            response = compute_mgmt_client.update_instance_pool(
                instance_pool_id=instance_pool_id,
                update_instance_pool_details=oci.core.models.UpdateInstancePoolDetails(
                    instance_configuration_id=new_instance_config_id
                )
            )
            print(f"Successfully updated Cluster Network {cluster_network_id}/Instance Pool {instance_pool_id} with new Instance Config {new_instance_config_id}")
        except oci.exceptions.ServiceError as e:
            print(f"Failed to update Cluster Network {cluster_network_id}/Instance Pool {instance_pool_id}: {e}")

# ------------------------------
# Attach Instance Config to GMC
# ------------------------------

def attach_instance_config_to_gpu_memory_cluster(gpu_memory_cluster_id, new_instance_config_id, compute_client):
    try:
        compute_client.update_compute_gpu_memory_cluster(
            gpu_memory_cluster_id=gpu_memory_cluster_id,
            update_compute_gpu_memory_cluster_details=oci.core.models.UpdateComputeGpuMemoryClusterDetails(
                instance_configuration_id=new_instance_config_id
            )
        )
        print(f"Successfully updated GPU Memory Cluster {gpu_memory_cluster_id} with new Instance Config {new_instance_config_id}")
    except oci.exceptions.ServiceError as e:
        print(f"Error updating GPU Memory Cluster {gpu_memory_cluster_id}: {e}")

# ------------------------------
# Main Function
# ------------------------------

def main():
    parser = argparse.ArgumentParser(description="Create and attach a new instance config with updated SSH key (full replication)")
    parser.add_argument("--compartment-id", required=True, help="OCID of the compartment")
    args = parser.parse_args()

    compartment_id = args.compartment_id

    # Authenticate with OCI using Instance Principals
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    compute_client = oci.core.ComputeClient(config={}, signer=signer)
    compute_mgmt_client = oci.core.ComputeManagementClient(config={}, signer=signer)

    # Step 1: List and choose an instance configuration
    chosen_instance_config = list_instance_configurations(compartment_id, compute_mgmt_client)
    if not chosen_instance_config:
        return

    # Step 2: Fetch instance configuration details for the selected configuration
    src_config = get_instance_config_details(chosen_instance_config.id, compute_mgmt_client)
    if not src_config:
        print("Failed to fetch instance configuration details.")
        return

    # Step 3: Ask for a new parameters (or leave blank to keep existing)
    new_ssh_key = input("\nEnter new SSH Public Key (leave blank to keep existing): ").strip()
    new_bv_size = input("\nEnter new BV Size (leave blank to keep existing): ").strip()
    if not new_bv_size:
        new_bv_size=0

    new_image_id = input("\nEnter new Image OCID (leave blank to keep existing): ").strip()
    new_cloud_init = input("\nEnter new cloud-init_path (leave blank to keep existing): ").strip()
    new_instance_config_name = input("\nEnter new instance config name (leave blank to keep existing): ").strip()
    # Step 5: Create a new instance configuration by replicating the source, replacing SSH key if provided
    new_instance_config = create_instance_configuration_from_details(compartment_id, src_config, new_ssh_key, int(new_bv_size), new_image_id, new_cloud_init, new_instance_config_name)
    if not new_instance_config:
        print("Failed to create new instance configuration.")
        return
    print(f"\nNew Instance Configuration Created: {new_instance_config.id}")

    # Step 6: Choose RDMA deployment type to update (ClusterNetwork or GPUMemoryCluster)
    rdma_deployment = input("\nChoose RDMA deployment type to update ([1]ClusterNetwork/[2]GPUMemoryCluster): ").strip().lower()

    if rdma_deployment in ("1", "clusternetwork"):
        cluster_networks, cluster_networks_instance_pools = list_cluster_networks(compartment_id, compute_mgmt_client)
        if not cluster_networks:
            print("No Cluster Networks found.")
            return None
        
        cluster_networks_using_instance_config = {}
        for cn_id, instance_pools in cluster_networks_instance_pools.items():
            cluster_networks_using_instance_config[cn_id] = []
            for instance_pool in instance_pools:
                if instance_pool.instance_configuration_id == src_config.id:
                    cluster_networks_using_instance_config[cn_id].append(instance_pool.id)
            else:
                if not cluster_networks_using_instance_config[cn_id]:
                    del cluster_networks_using_instance_config[cn_id]
        print(f"\nFound {len(cluster_networks_using_instance_config)}/{len(cluster_networks)} Cluster Networks in compartment {compartment_id} using the instance configuration {src_config.display_name}.")
        
        update_mode = input("\nChoose update mode ([1]Update all using selected instance config/[2]Update specific): ").strip().lower()
        if update_mode == "1":
            for cn_id, instance_pool_ids in cluster_networks_using_instance_config.items():
                attach_instance_config_to_cluster_network(cn_id, instance_pool_ids, new_instance_config.id, compute_mgmt_client)
            print("\nSuccess! Now you can add new nodes to the cluster using this instance configuration.")

        elif update_mode == "2":
            for idx, network in enumerate(cluster_networks, 1):
                print(f"{idx}. {network.display_name} ({network.id})")
            choice = int(input("\nEnter the number of the Cluster Network to use: ")) - 1
            if choice < 0 or choice >= len(cluster_networks):
                print("Invalid choice.")
                return
            instance_pool_ids = [entry.id for entry in cluster_networks_instance_pools[cluster_networks[choice].id]]
            attach_instance_config_to_cluster_network(cluster_networks[choice].id, instance_pool_ids, new_instance_config.id, compute_mgmt_client)
            print("\nSuccess! Now you can add new nodes to the cluster using this instance configuration.")
        else:
            return

    elif rdma_deployment in ("2", "gpumemorycluster"):
        gpu_memory_clusters = list_compute_gpu_memory_clusters(compartment_id, compute_client)
        if not gpu_memory_clusters:
            print("No GPU Memory Clusters found.")
            return None
        
        gmcs_using_instance_config = []
        for gmc in gpu_memory_clusters:
            if gmc.instance_configuration_id == src_config.id:
                gmcs_using_instance_config.append(gmc)
        print(f"\nFound {len(gmcs_using_instance_config)}/{len(gpu_memory_clusters)} GPU Memory Clusters in compartment {compartment_id} using the instance configuration {src_config.display_name}.")
        
        update_mode = input("\nChoose update mode ([1]Update all using selected instance config/[2]Update specific): ").strip().lower()
        if update_mode == "1":
            for entry in gmcs_using_instance_config:
                attach_instance_config_to_gpu_memory_cluster(entry.id, new_instance_config.id, compute_client)
            print("\nSuccess! The new nodes in these GMCs will use the new instance configuration.")
        elif update_mode == "2":
            for idx, gmc in enumerate(gpu_memory_clusters, 1):
                print(f"{idx}. {gmc.display_name} ({gmc.id})")
            choice = int(input("\nEnter the number of the GPU Memory Cluster to use: ")) - 1
            if choice < 0 or choice >= len(gpu_memory_clusters):
                print("Invalid choice.")
                return
            attach_instance_config_to_gpu_memory_cluster(gpu_memory_clusters[choice].id, new_instance_config.id, compute_client)
            print("\nSuccess! The new nodes in these GMCs will use the new instance configuration.")
        else:
            return
    else:
        print("Invalid work mode.")
        return

if __name__ == "__main__":
    main()