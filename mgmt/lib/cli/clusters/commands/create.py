
import click
from lib.logger import logger
from lib.ociwrap import create_cluster,get_memory_fabrics
from lib.database import get_config_by_name, get_controller_node


import socket
### 
### Add a node to the cluster
###

@click.command()
@click.option('--count', type=int, required=True, help='Number of nodes to add, if you use 0 for a memory cluster, it will do the max available')
@click.option('--cluster', required=True, help='Specify the name of the cluster')
@click.option('--instancetype', required=True, help='Specify the instance type of the cluster')
@click.option('--names', required=False, help='comma separated list of host names')
@click.option('--fabric', required=False, help='OCID of the memory fabric to add the nodes in for GMF based nodes')
@click.option('--memorycluster', required=False, help='Name used for the memory cluster, default will be cluster_xxxxx with xxxxx the last 5 character of the fabric ocid')
def create(count,cluster,instancetype,names,fabric,memorycluster):
    """Create a new cluster.\n
    Example:\n
    # Create a standard compute cluster\n

    mgmt clusters create --count 3 --cluster mycluster --instancetype BM.Standard.E3.128\n

    # Create a GPU cluster with memory fabric\n

    mgmt clusters create --count 2 --cluster mycluster --instancetype BM.GPU.GB200.4 --fabric ocid1.fabric.oc1..xxxx
    --names node01,node02\n"""
    if names:
        name_list=names.split(',')
        if count != len(name_list):
            click.echo("The names does not match the count, exiting")
            exit(1)
    else:
        name_list=[]
    config = get_config_by_name(instancetype)
    controller = get_controller_node()
    if controller is None:
        controller_hostname=socket.gethostname()
    else:
        controller_hostname=controller.hostname
    if fabric is None:
        gpu_memory_cluster_name = None
        if "GPU.GB" in config.shape:
            available_fabric=[]
            tenancy = controller.tenancy_id
            fabric_list=get_memory_fabrics(tenancy,get_controller_node().compartment_id)
            if len(fabric_list):
                for fabric_item in fabric_list:
                    if fabric_item[2] is None:
                        available_fabric.append({"ocid":fabric_item[0].id,"available":int(fabric_item[4]['AVAILABLE'])})
                available_fabric.sort(key=lambda x: x['available'], reverse=True)
            if available_fabric:
                fabric=available_fabric[0]['ocid']
                if count == 0:
                    count=available_fabric[0]['available']

    if memorycluster is None and fabric is not None:
        gpu_memory_cluster_name = cluster+"_"+fabric[-5:]
    else:
        gpu_memory_cluster_name=memorycluster
    if gpu_memory_cluster_name is None and fabric is None:
        logger.info(f"Creating cluster {cluster} with {count} nodes")
    else:
        logger.info(f"Creating cluster {cluster} with {count} nodes on memoryfabric {fabric} with gpu_memory_cluster_name {gpu_memory_cluster_name}")
    create_cluster(config,int(count),cluster,controller_hostname, name_list, gpu_memory_fabric=fabric, gpu_memory_cluster_name=gpu_memory_cluster_name)
    

