from rich.table import Table
from rich.console import Console
import yaml, json
from collections import defaultdict
import sys

def print_config_info(configuration):
    table = Table(show_header=False, show_lines=True)
    table.add_column(justify="left")
    table.add_column(justify="left")
    table.add_row("name", str(configuration.name))
    table.add_row("role", str(configuration.role))
    table.add_row("partition", str(configuration.partition))
    table.add_row("default_partition", str(configuration.default_partition))
    table.add_row("shape", str(configuration.shape))
    table.add_row("change_hostname", str(configuration.change_hostname))
    table.add_row("hostname_convention", str(configuration.hostname_convention))
    table.add_row("permanent", str(configuration.permanent))
    table.add_row("rdma_enabled", str(configuration.rdma_enabled))
    table.add_row("stand_alone", str(configuration.stand_alone))
    table.add_row("max_number_nodes", str(configuration.stand_alone))
    table.add_row("region", str(configuration.region))
    table.add_row("availability_domain", str(configuration.availability_domain))
    table.add_row("private_subnet_cidr", str(configuration.private_subnet_cidr))
    table.add_row("private_subnet_id", str(configuration.private_subnet_id))
    table.add_row("target_compartment_id", str(configuration.target_compartment_id))
    table.add_row("use_marketplace_image", str(configuration.use_marketplace_image))
    table.add_row("marketplace_listing", str(configuration.marketplace_listing))
    table.add_row("image_id", str(configuration.image_id))
    table.add_row("boot_volume_size", str(configuration.boot_volume_size))
    table.add_row("instance_pool_ocpus", str(configuration.instance_pool_ocpus))
    table.add_row("instance_pool_custom_memory", str(configuration.instance_pool_custom_memory))
    table.add_row("instance_pool_memory", str(configuration.instance_pool_memory))
    table.add_row("hyperthreading", str(configuration.hyperthreading))
    table.add_row("preemptible", str(configuration.preemptible))
    console = Console()
    console.print(table)

def print_config_list(configurations, title):
    table = Table(title=title)
    table.add_column("name", justify="left",no_wrap=True)
    table.add_column("role", justify="left")
    table.add_column("partition", justify="left")
    table.add_column("default_partition", justify="left")
    table.add_column("shape", justify="left")
    table.add_column("hostname_convention", justify="left")
    table.add_column("permanent", justify="left")
    table.add_column("rdma_enabled", justify="left")
    table.add_column("stand_alone", justify="left")
    table.add_column("max_number_nodes", justify="left")
    table.add_column("region", justify="left")
    table.add_column("availability_domain", justify="left")
    table.add_column("private_subnet_cidr", justify="left")
    table.add_column("private_subnet_id", justify="left")
    table.add_column("target_compartment_id", justify="left")
    table.add_column("image_id", justify="left")
    table.add_column("boot_volume_size", justify="left")
    table.add_column("instance_pool_ocpus", justify="left")
    table.add_column("instance_pool_memory", justify="left")
    table.add_column("hyperthreading", justify="left")
    table.add_column("preemptible", justify="left")
         
    for configuration in configurations:
        hostname_convention=None
        if configuration.change_hostname:
            hostname_convention=configuration.hostname_convention
        image_display_field=configuration.image_id
        if configuration.use_marketplace_image:
             image_display_field=configuration.marketplace_listing
        memory_display_field="Default"
        if configuration.instance_pool_custom_memory:
             memory_display_field=configuration.instance_pool_memory
             
        table.add_row(str(configuration.name), 
                      str(configuration.role), 
                      str(configuration.partition), 
                      str(configuration.default_partition), 
                      str(configuration.shape), 
                      str(hostname_convention), 
                      str(configuration.permanent), 
                      str(configuration.rdma_enabled), 
                      str(configuration.stand_alone), 
                      str(configuration.max_number_nodes), 
                      str(configuration.region), 
                      str(configuration.availability_domain), 
                      str(configuration.private_subnet_cidr), 
                      str(configuration.private_subnet_id), 
                      str(configuration.target_compartment_id), 
                      str(image_display_field), 
                      str(configuration.boot_volume_size), 
                      str(configuration.instance_pool_ocpus), 
                      str(memory_display_field), 
                      str(configuration.hyperthreading), 
                      str(configuration.preemptible)
                      )

    console = Console()
    console.print(table)

def print_config_list_yaml_json(configurations,output_file=None,type="yaml"):
    queues = defaultdict(list)

    for config in configurations:
        instance_type = {
            "name": config.name,
            "role": config.role,
            "default": False,  # we'll update this below
            "shape": config.shape,
            "change_hostname": config.change_hostname,  # fallback logic
            "hostname_convention": config.hostname_convention,  # fallback logic
            "permanent": config.permanent,
            "rdma_enabled": config.rdma_enabled,
            "stand_alone": config.stand_alone,
            "max_number_nodes": config.max_number_nodes,
            "max_cluster_size": 50,
            "max_cluster_count": 1000,
            "region": config.region,
            "availability_domain": config.availability_domain,
            "private_subnet": config.private_subnet_cidr,
            "private_subnet_id": config.private_subnet_id,
            "image_id": config.image_id,
            "target_compartment_id": config.target_compartment_id,
            "boot_volume_size": config.boot_volume_size,
            "use_marketplace_image": config.use_marketplace_image,
            "use_compute_agent": True,
            "instance_pool_ocpus": config.instance_pool_ocpus,
            "instance_pool_memory": config.instance_pool_memory,
            "instance_pool_custom_memory": config.instance_pool_custom_memory,
            "marketplace_listing": config.marketplace_listing,
            "hyperthreading": config.hyperthreading,
            "preemptible": config.preemptible
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

    if type == "yaml":
        if output_file is None:
            yaml.dump(final_yaml, sys.stdout, sort_keys=False, default_flow_style=False)
        else:
            with open(output_file, "w") as f:
                yaml.dump(final_yaml, f, sort_keys=False, default_flow_style=False)
    else:
        if output_file is None:
            print(json.dumps(final_yaml, indent=4))
        else:
            with open(output_file, "w") as f:
                f.write(json.dumps(final_yaml, indent=4))