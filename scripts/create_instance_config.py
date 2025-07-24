#!/usr/bin/env python3

import oci
import argparse
import inspect

def list_compartments(identity_client, tenancy_id):
    compartments = []
    response = identity_client.list_compartments(
        compartment_id=tenancy_id,
        compartment_id_in_subtree=True,
        access_level="ACCESSIBLE"
    )
    compartments.extend(response.data)

    # Sort by name for readability
    compartments = sorted(compartments, key=lambda c: c.name.lower())

    print("\nAvailable Compartments:")
    print(f"0. {tenancy_id} (root tenancy)")
    for idx, c in enumerate(compartments, start=1):
        print(f"{idx}. {c.name} ({c.id})")

    choice = int(input("\nEnter the compartment to use: "))
    if choice == 0:
        return tenancy_id
    elif 1 <= choice <= len(compartments):
        return compartments[choice - 1].id
    else:
        print("Invalid choice.")
        return None

def list_instance_configurations(compartment_id, compute_mgmt_client):
    response = compute_mgmt_client.list_instance_configurations(compartment_id=compartment_id)
    instance_configs = response.data
    if not instance_configs:
        print("No instance configurations found.")
        return None
    print("\nAvailable Instance Configurations:")
    for idx, config in enumerate(instance_configs, 1):
        print(f"{idx}. {config.display_name} ({config.id})" if config.id else f"{idx}. {config.display_name}")
    choice = int(input("\nEnter the the instance config to use: ")) - 1
    return instance_configs[choice] if 0 <= choice < len(instance_configs) else None

def get_instance_config_details(instance_config_id, compute_mgmt_client):
    response = compute_mgmt_client.get_instance_configuration(instance_config_id)
    return response.data

def list_cluster_networks(compartment_id, compute_mgmt_client):
    response = compute_mgmt_client.list_cluster_networks(compartment_id=compartment_id)
    cluster_networks = response.data
    if not cluster_networks:
        print("No Cluster Networks found.")
        return None
    print("\nAvailable Cluster Networks:")
    for idx, network in enumerate(cluster_networks, 1):
        print(f"{idx}. {network.display_name} ({network.id})")
    choice = int(input("\nEnter the Cluster Network to use: ")) - 1
    return cluster_networks[choice] if 0 <= choice < len(cluster_networks) else None

def create_instance_configuration_from_details(compartment_id, src_config, new_ssh_key, new_bv_size, new_image_id):
    try:
        launch = src_config.instance_details.launch_details

        new_metadata = dict(launch.metadata) if launch.metadata else {}
        if new_ssh_key:
            new_metadata["ssh_authorized_keys"] = new_ssh_key

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

        new_create_vnic = None
        if launch.create_vnic_details:
            new_create_vnic = oci.core.models.InstanceConfigurationCreateVnicDetails(
                assign_public_ip=launch.create_vnic_details.assign_public_ip,
                assign_private_dns_record=launch.create_vnic_details.assign_private_dns_record,
                subnet_id=launch.create_vnic_details.subnet_id
            )

        src_details = launch.source_details
        bv_size = new_bv_size if new_bv_size else getattr(src_details, 'boot_volume_size_in_gbs', None)
        image_id = new_image_id if new_image_id else getattr(src_details, 'image_id', None)

        new_source_details = oci.core.models.InstanceConfigurationInstanceSourceViaImageDetails(
            source_type=src_details.source_type,
            image_id=image_id,
            boot_volume_size_in_gbs=bv_size,
            boot_volume_vpus_per_gb=getattr(src_details, 'boot_volume_vpus_per_gb', None)
        )

        # Dynamically filter valid args for InstanceConfigurationLaunchInstanceDetails
        launch_attrs = {
            'availability_domain': getattr(launch, "availability_domain", None),
            'compartment_id': src_config.compartment_id,
            'display_name': getattr(launch, "display_name", "replica"),
            'shape': getattr(launch, "shape", None),
            'shape_config': getattr(launch, "shape_config", None),
            'platform_config': getattr(launch, "platform_config", None),
            'metadata': new_metadata,
            'extended_metadata': getattr(launch, "extended_metadata", None),
            'ipxe_script': getattr(launch, "ipxe_script", None),
            'freeform_tags': getattr(launch, "freeform_tags", None),
            'defined_tags': getattr(launch, "defined_tags", None),
            'agent_config': new_agent_config,
            'create_vnic_details': new_create_vnic,
            'source_details': new_source_details,
            'launch_options': getattr(launch, "launch_options", None),
            'fault_domain': getattr(launch, "fault_domain", None),
            'dedicated_vm_host_id': getattr(launch, "dedicated_vm_host_id", None),
            'launch_mode': getattr(launch, "launch_mode", None),
            'instance_options': getattr(launch, "instance_options", None),
            'availability_config': getattr(launch, "availability_config", None),
            'preemptible_instance_config': getattr(launch, "preemptible_instance_config", None),
            'security_attributes': getattr(launch, "security_attributes", None),
            'licensing_configs': getattr(launch, "licensing_configs", None)
        }

        valid_params = inspect.signature(
            oci.core.models.InstanceConfigurationLaunchInstanceDetails
        ).parameters
        filtered_launch_attrs = {
            k: v for k, v in launch_attrs.items()
            if k in valid_params and v is not None
        }
        filtered_launch_attrs['compartment_id'] = src_config.compartment_id
        filtered_launch_attrs['shape'] = launch.shape
        filtered_launch_attrs['source_details'] = new_source_details

        new_launch_details = oci.core.models.InstanceConfigurationLaunchInstanceDetails(**filtered_launch_attrs)

        new_instance_details = oci.core.models.ComputeInstanceDetails(
            instance_type=src_config.instance_details.instance_type,
            launch_details=new_launch_details,
            block_volumes=getattr(src_config.instance_details, "block_volumes", None),
            secondary_vnics=getattr(src_config.instance_details, "secondary_vnics", None)
        )

        new_config_details = oci.core.models.CreateInstanceConfigurationDetails(
            compartment_id=src_config.compartment_id,
            display_name=src_config.display_name + "-copy",
            instance_details=new_instance_details,
            defined_tags=getattr(src_config, "defined_tags", None),
            freeform_tags=getattr(src_config, "freeform_tags", None)
        )

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
            compute_mgmt_client.update_instance_pool(
                instance_pool_id=pool_id,
                update_instance_pool_details=update_details
            )
            print(f"Successfully updated Instance Pool {pool_id} with new Instance Config {new_instance_config_id}")
        except oci.exceptions.ServiceError as e:
            print(f"Failed to update Instance Pool {pool_id}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Create and attach a new instance config with updated SSH key (full replication)")

    args = parser.parse_args()

    # Authenticate
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    identity_client = oci.identity.IdentityClient(config={}, signer=signer)

    # Get tenancy ID from instance metadata
    tenancy_id = signer.tenancy_id

    # Let user pick compartment interactively
    compartment_id = list_compartments(identity_client, tenancy_id)
    if not compartment_id:
        print("No compartment selected. Exiting.")
        return

    compute_mgmt_client = oci.core.ComputeManagementClient(config={}, signer=signer)

    chosen_instance_config = list_instance_configurations(compartment_id, compute_mgmt_client)
    if not chosen_instance_config:
        return

    src_config = get_instance_config_details(chosen_instance_config.id, compute_mgmt_client)
    if not src_config:
        print("Failed to fetch instance configuration details.")
        return

    new_ssh_key = input("\nEnter new SSH Public Key (leave blank to keep existing): ").strip()
    new_bv_size = input("\nEnter new BV Size (leave blank to keep existing): ").strip()
    new_bv_size = int(new_bv_size) if new_bv_size else None
    new_image_id = input("\nEnter new Image OCID (leave blank to keep existing): ").strip()

    new_instance_config = create_instance_configuration_from_details(
        compartment_id, src_config, new_ssh_key, new_bv_size, new_image_id
    )
    if not new_instance_config:
        print("Failed to create new instance configuration.")
        return
    print(f"\nNew Instance Configuration Created: {new_instance_config.id}")

    chosen_cluster_network = list_cluster_networks(compartment_id, compute_mgmt_client)
    if not chosen_cluster_network:
        return

    attach_instance_config_to_cluster_network(
        chosen_cluster_network.id, new_instance_config.id, compute_mgmt_client
    )
    print(f"\nInstance Configuration {new_instance_config.id} attached to Cluster Network {chosen_cluster_network.id}")
    print("\nSuccess! Now you can add new nodes to the cluster using this instance configuration.")

if __name__ == "__main__":
    main()
