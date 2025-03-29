#!/usr/bin/env python3

import oci
import argparse

def list_instance_configurations(compartment_id, compute_mgmt_client):
    """
    Lists available instance configurations in the compartment and lets the user choose one.
    Returns the selected instance configuration object.
    """
    response = compute_mgmt_client.list_instance_configurations(compartment_id=compartment_id)
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
    response = compute_mgmt_client.list_cluster_networks(compartment_id=compartment_id)
    cluster_networks = response.data
    if not cluster_networks:
        print("No Cluster Networks found.")
        return None
    print("\nAvailable Cluster Networks:")
    for idx, network in enumerate(cluster_networks, 1):
        print(f"{idx}. {network.display_name} ({network.id})")
    choice = int(input("\nEnter the number of the Cluster Network to use: ")) - 1
    return cluster_networks[choice] if 0 <= choice < len(cluster_networks) else None

# ------------------------------
# Core Function: Full Replication with SSH Key Replacement
# ------------------------------

def create_instance_configuration_from_details(compartment_id, src_config, new_ssh_key, new_bv_size, new_image_id):
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
                subnet_id=launch.create_vnic_details.subnet_id
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
            licensing_configs=launch.licensing_configs
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
            display_name=src_config.display_name + "-copy",
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

def attach_instance_config_to_cluster_network(cluster_network_id, new_instance_config_id, compute_mgmt_client):
    try:
        cluster_network = compute_mgmt_client.get_cluster_network(cluster_network_id).data
    except oci.exceptions.ServiceError as e:
        print(f"Error fetching cluster network details: {e}")
        return
    instance_pool_ids = [pool.id for pool in cluster_network.instance_pools]
    if not instance_pool_ids:
        print(f"No instance pools found in Cluster Network {cluster_network_id}. Cannot attach instance config.")
        return
    print(f"Found {len(instance_pool_ids)} instance pool(s) in Cluster Network.")
    for pool_id in instance_pool_ids:
        update_details = oci.core.models.UpdateInstancePoolDetails(
            instance_configuration_id=new_instance_config_id
        )
        try:
            response = compute_mgmt_client.update_instance_pool(
                instance_pool_id=pool_id,
                update_instance_pool_details=update_details
            )
            print(f"Successfully updated Instance Pool {pool_id} with new Instance Config {new_instance_config_id}")
        except oci.exceptions.ServiceError as e:
            print(f"Failed to update Instance Pool {pool_id}: {e}")
    print("\nNow you can add new nodes to the cluster.")

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

    # Step 3: Ask for a new SSH public key (or leave blank to keep existing key)
    new_ssh_key = input("\nEnter new SSH Public Key (leave blank to keep existing): ").strip()
    new_bv_size = input("\nEnter new BV Size (leave blank to keep existing): ").strip()
    if not new_bv_size:
        new_bv_size=0

    new_image_id = input("\nEnter new Image OCID (leave blank to keep existing): ").strip()


    # Step 4: Create a new instance configuration by replicating the source, replacing SSH key if provided
    new_instance_config = create_instance_configuration_from_details(compartment_id, src_config, new_ssh_key, int(new_bv_size), new_image_id)
    if not new_instance_config:
        print("Failed to create new instance configuration.")
        return
    print(f"\nNew Instance Configuration Created: {new_instance_config.id}")

    # Step 5: List and choose a Cluster Network to attach the new instance config
    chosen_cluster_network = list_cluster_networks(compartment_id, compute_mgmt_client)
    if not chosen_cluster_network:
        return

    # Step 6: Attach the new instance configuration to the chosen Cluster Network
    attach_instance_config_to_cluster_network(chosen_cluster_network.id, new_instance_config.id, compute_mgmt_client)
    print(f"\nInstance Configuration {new_instance_config.id} attached to Cluster Network {chosen_cluster_network.id}")

    print("\nSuccess! Now you can add new nodes to the cluster using this instance configuration.")

if __name__ == "__main__":
    main()