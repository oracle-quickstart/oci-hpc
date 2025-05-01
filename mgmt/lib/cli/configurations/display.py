from rich.table import Table
from rich.console import Console
import yaml
from collections import defaultdict

def print_config_info(configurations):
    for configuration in configurations:
        table = Table(show_header=False, show_lines=True)
        table.add_column(justify="left")
        table.add_column(justify="left")
        table.add_row("Name", configuration.name)
        table.add_row("Partition", configuration.partition)
        table.add_row("Shape", configuration.shape)
        table.add_row("Change Hostname", configuration.change_hostname)
        table.add_row("Hostname Convention", configuration.hostname_convention)
        table.add_row("Permanent", configuration.permanent)
        table.add_row("RDMA-Enabled", configuration.rdma_enabled)
        table.add_row("Stand-Alone", configuration.stand_alone)
        table.add_row("Region", configuration.region)
        table.add_row("Availability Domain", configuration.ad)
        table.add_row("Subnet CIDR", configuration.private_subnet_cidr)
        table.add_row("Subnet OCID", configuration.private_subnet_id)
        table.add_row("Compartment", configuration.targetCompartment)
        table.add_row("Use Marketplace Image", configuration.use_marketplace_image)
        table.add_row("Marketplace Listing", configuration.marketplace_listing)
        table.add_row("Image", configuration.image)
        table.add_row("Boot Volume Size", configuration.boot_volume_size)
        table.add_row("Instances OCPU", configuration.instance_pool_ocpus)
        table.add_row("Instance Select Custom Memory", configuration.instance_pool_custom_memory)
        table.add_row("Instance Memory", configuration.instance_pool_memory)
        table.add_row("Hyperthreading", configuration.hyperthreading)
    console = Console()
    console.print(table)

def print_config_list(configurations, title):
    table = Table(title=title)
    table.add_column("Name", justify="left")
    table.add_column("Partition", justify="left")
    table.add_column("Shape", justify="left")
    table.add_column("Hostname Convention", justify="left")
    table.add_column("Permanent", justify="left")
    table.add_column("RDMA-Enabled", justify="left")
    table.add_column("Stand-Alone", justify="left")
    table.add_column("Region", justify="left")
    table.add_column("Availability Domain", justify="left")
    table.add_column("Subnet CIDR", justify="left")
    table.add_column("Subnet OCID", justify="left")
    table.add_column("Compartment", justify="left")
    table.add_column("Image", justify="left")
    table.add_column("BV Size", justify="left")
    table.add_column("OCPU", justify="left")
    table.add_column("Memory", justify="left")
    table.add_column("Hyperthreading", justify="left")
         
    for configuration in configurations:
        image_display_field=configuration.image
        if configuration.use_marketplace_image:
             image_display_field=configuration.marketplace_listing
        memory_display_field="Default"
        if configuration.instance_pool_custom_memory:
             memory_display_field=configuration.instance_pool_memory
             
        table.add_row(str(configuration.name), 
                      str(configuration.partition), 
                      str(configuration.shape), 
                      str(configuration.hostname_convention), 
                      str(configuration.permanent), 
                      str(configuration.rdma_enabled), 
                      str(configuration.stand_alone), 
                      str(configuration.region), 
                      str(configuration.ad), 
                      str(configuration.private_subnet_cidr), 
                      str(configuration.private_subnet_id), 
                      str(configuration.targetCompartment), 
                      str(image_display_field), 
                      str(configuration.boot_volume_size), 
                      str(configuration.instance_pool_ocpus), 
                      str(memory_display_field), 
                      str(configuration.hyperthreading)
                      )

    console = Console()
    console.print(table)

def print_config_list_yaml(configurations,output_file):
    queues = defaultdict(list)

    for config in configurations:
        instance_type = {
            "name": config.name,
            "default": False,  # we'll update this below
            "shape": config.shape,
            "change_hostname": config.change_hostname,  # fallback logic
            "hostname_convention": config.hostname_convention,  # fallback logic
            "permanent": config.permanent,
            "rdma_enabled": config.rdma_enabled,
            "stand_alone": config.stand_alone,
            "max_number_nodes": 1000,
            "max_cluster_size": 50,
            "max_cluster_count": 1000,
            "region": config.region,
            "ad": config.ad,
            "private_subnet": config.private_subnet_cidr,
            "private_subnet_id": config.private_subnet_id,
            "image": config.image,
            "targetCompartment": config.targetCompartment,
            "boot_volume_size": config.boot_volume_size,
            "use_marketplace_image": config.use_marketplace_image,
            "use_compute_agent": True,
            "instance_pool_ocpus": config.instance_pool_ocpus,
            "instance_pool_memory": config.instance_pool_memory,
            "instance_pool_custom_memory": config.instance_pool_custom_memory,
            "marketplace_listing": config.marketplace_listing,
            "hyperthreading": config.hyperthreading,
        }
        queues[config.partition].append(instance_type)

    yaml_queues = []
    for idx, (partition, instances) in enumerate(queues.items()):
        for i, inst in enumerate(instances):
            inst["default"] = (i == 0)
        yaml_queues.append({
            "name": partition,
            "default": (idx == 0),
            "instance_types": instances
        })

    final_yaml = {"queues": yaml_queues}

    with open(output_file, "w") as f:
        yaml.dump(final_yaml, f, sort_keys=False, default_flow_style=False)