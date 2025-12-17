from rich.table import Table
from rich.console import Console
import yaml, json
from collections import defaultdict
import sys
from ClusterShell.NodeSet import NodeSet

def print_image_list(images, title,nodes_per_image=None):
    table = Table(title=title)
    table.add_column("name", justify="left",no_wrap=True)
    table.add_column("ocid", justify="left")
    if nodes_per_image:
        table.add_column("nodes", justify="left")
         
    for image in images:
        if nodes_per_image:
            table.add_row(str(image.display_name), 
                      str(image.id),
                      str(NodeSet(",".join(nodes_per_image[image.id])))
                      )
        else:
            table.add_row(str(image.display_name), 
                      str(image.id),
                      str(image.lifecycle_state)
                      )

    console = Console()
    console.print(table)

def print_image_list_yaml_json(images,output_file=None,type="yaml",nodes_per_image=None):
    images_print = list

    for image in images:
        image_type = {
            "name": image.display_name,
            "id": image.id
        }
        if nodes_per_image:
            image_type["nodes"] = str(NodeSet(",".join(nodes_per_image[image.id])))
        images_print.append(image_type)



    final_yaml = {"images": images_print}

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