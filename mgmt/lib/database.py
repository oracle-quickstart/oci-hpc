from sqlalchemy import Column, Integer, String, Boolean, Enum, or_, and_, not_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.inspection import inspect

import logging
import sys

import yaml

from datetime import datetime, timedelta, timezone
version = sys.version_info
if version >= (3, 12):
    UTC = timezone.utc

Base = declarative_base()

class Nodes(Base):
    __tablename__ = 'nodes' 

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String(128), unique=True, nullable=True)
    controller_status = Column(Enum('configuring', 'reconfiguring', 'terminating', 'waiting_for_info', 'configured', 'terminated'), nullable=True)
    started_time = Column(String(128), nullable=True)
    status = Column(Enum('starting', 'terminating', 'terminated', 'running', 'unreachable'), nullable=True)
    availability_domain = Column(String(128), nullable=True)
    first_time_reachable = Column(String(128), nullable=True)
    cluster_name = Column(String(128), nullable=True)
    compartment_id = Column(String(128), nullable=True)
    tenancy_id = Column(String(128), nullable=True)
    compute_status = Column(Enum('configuring', 'configured'), nullable=True)
    controller_name = Column(String(128), nullable=True)
    fss_mount = Column(String(128), nullable=True)
    gpu_memory_fabric = Column(String(128), nullable=True)
    hostname = Column(String(128), unique=True, nullable=True)
    hpc_island = Column(String(128), nullable=True)
    image_id = Column(String(128), nullable=True)
    last_time_reachable = Column(String(128), nullable=True)
    oci_name = Column(String(128), nullable=True)
    ocid = Column(String(128), unique=True, nullable=True)
    rack_id = Column(String(128), nullable=True)
    rail_id = Column(String(128), nullable=True)
    network_block_id = Column(String(128), nullable=True)
    memory_cluster_name = Column(String(128), nullable=True)
    role = Column(String(128), nullable=True)
    serial = Column(String(128), nullable=True)
    shape = Column(String(128), nullable=True)
    terminated_time = Column(String(128), nullable=True)
    update_count = Column(Integer, nullable=True)
    healthcheck_recommendation = Column(String(128), nullable=True)
    last_healthcheck_time = Column(String(128), nullable=True)
    healthcheck_logs = Column(String(1024), nullable=True)
    oci_health = Column(String(128), nullable=True)
    oci_impacted_components = Column(Boolean, default=True, nullable=False)
    oci_host_id = Column(String(128), nullable=True)

class TerminatedNodes(Base):
    __tablename__ = 'terminated_nodes' 

    id = Column(Integer, primary_key=True, autoincrement=True)
    ip_address = Column(String(128), nullable=True)
    controller_status = Column(Enum('configuring', 'reconfiguring', 'terminating', 'waiting_for_info', 'configured', 'terminated'), nullable=True)
    started_time = Column(String(128), nullable=True)
    status = Column(Enum('starting', 'terminating', 'terminated', 'running', 'unreachable'), nullable=True)
    availability_domain = Column(String(128), nullable=True)
    first_time_reachable = Column(String(128), nullable=True)
    cluster_name = Column(String(128), nullable=True)
    compartment_id = Column(String(128), nullable=True)
    tenancy_id = Column(String(128), nullable=True)
    compute_status = Column(Enum('configuring', 'configured'), nullable=True)
    controller_name = Column(String(128), nullable=True)
    fss_mount = Column(String(128), nullable=True)
    gpu_memory_fabric = Column(String(128), nullable=True)
    hostname = Column(String(128), nullable=True)
    hpc_island = Column(String(128), nullable=True)
    image_id = Column(String(128), nullable=True)
    last_time_reachable = Column(String(128), nullable=True)
    oci_name = Column(String(128), nullable=True)
    ocid = Column(String(128), unique=True, nullable=True)
    rack_id = Column(String(128), nullable=True)
    rail_id = Column(String(128), nullable=True)
    network_block_id = Column(String(128), nullable=True)
    memory_cluster_name = Column(String(128), nullable=True)
    role = Column(String(128), nullable=True)
    serial = Column(String(128), nullable=True)
    shape = Column(String(128), nullable=True)
    terminated_time = Column(String(128), nullable=True)
    update_count = Column(Integer, nullable=True)
    healthcheck_recommendation = Column(String(128), nullable=True)
    last_healthcheck_time = Column(String(128), nullable=True)
    healthcheck_logs = Column(String(1024), nullable=True)
    oci_health = Column(String(128), nullable=True)
    oci_impacted_components = Column(Boolean, default=True, nullable=False)
    oci_host_id = Column(String(128), nullable=True)

class Configurations(Base):
    __tablename__ = 'configurations' 
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    partition = Column(String(64), nullable=False)
    shape = Column(String(64), nullable=False)
    change_hostname = Column(Boolean, default=True, nullable=False)
    hostname_convention = Column(String(64), nullable=True)
    permanent = Column(Boolean, default=True, nullable=False)
    rdma_enabled = Column(Boolean, default=True, nullable=False)
    stand_alone = Column(Boolean, default=False, nullable=False)
    region = Column(String(64), nullable=True)
    availability_domain = Column(String(64), nullable=True)
    private_subnet_cidr = Column(String(64), nullable=True)
    private_subnet_id = Column(String(128), nullable=True)
    image_id = Column(String(128), nullable=True)
    target_compartment_id = Column(String(128), nullable=True)
    boot_volume_size = Column(Integer, nullable=True)
    use_marketplace_image = Column(Boolean, default=False, nullable=False)
    instance_pool_ocpus = Column(Integer, nullable=True)
    instance_pool_custom_memory = Column(Boolean, default=False, nullable=False)
    instance_pool_memory = Column(Integer, nullable=True)
    marketplace_listing = Column(String(64), nullable=True)
    hyperthreading = Column(Boolean, default=True, nullable=False)
    preemptible = Column(Boolean, default=False, nullable=False)

logger = logging.getLogger(__name__)

def query_db():
    try:
        # DB Connection Details
        db_host = "localhost"
        db_user = "clusterUser"
        db_pw = "Cluster1234!"
        db_name = "clusterDB"
        
        # Create the SQLAlchemy engine
        connection_string = f"mysql+pymysql://{db_user}:{db_pw}@{db_host}/{db_name}"
        engine = create_engine(connection_string)
        
        # Create a session factory
        Session = sessionmaker(bind=engine)
        session = Session()
        
        return session
    except Exception as e:
        logger.error(f"Error connecting to the database: {e}")
        sys.exit(1)

def node_to_dict(node):
    return {
        c.key: getattr(node, c.key)
        for c in inspect(node).mapper.column_attrs
    }

def get_all_nodes():
    """Get all nodes/servers from the database"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.status != "terminated").all()
        return nodes
    finally:
        session.close()

def get_all_compute_nodes():
    """Get all nodes/servers from the database"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(and_(
            Nodes.role == "compute",
            Nodes.status != "terminated"
            )
        ).all()
        return nodes
    finally:
        session.close()

def get_all_management_nodes():
    """Get all nodes/servers from the database"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(and_(
            Nodes.role != "compute",
            Nodes.status != "terminated"
            )
        ).all()
        return nodes
    finally:
        session.close()

def get_controller_node():
    """Get the controller from the database"""
    session = query_db()
    try:
        node = session.query(Nodes).filter(and_(
            Nodes.role == "controller",
            Nodes.status != "terminated"
            )
        ).first()
        return node
    finally:
        session.close() 

def get_all_terminated_nodes():
    """Get all nodes/servers from the database"""
    session = query_db()
    try:
        nodes = session.query(TerminatedNodes).all()
        return nodes
    finally:
        session.close()

def get_all_nodes_to_configure():
    """Get all nodes/servers from the database"""
    session = query_db()
    try:
        nodes_configuring = session.query(Nodes).filter(Nodes.controller_status.in_(['configuring', 'reconfiguring'])).all()
        nodes_terminating = session.query(Nodes).filter(Nodes.controller_status.in_(['terminating'])).all()
        return nodes_configuring,nodes_terminating
    finally:
        session.close()

def get_all_nodes_failing_to_start(unreachable_timeout,node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    session = query_db()
    nodes_failing_to_start=[]
    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    time_th = (current_time - unreachable_timeout).replace(tzinfo=timezone.utc)
    try:
        if node_any_list:
            nodes_waiting_for_info = session.query(Nodes).filter(            
                and_(
                    Nodes.controller_status.in_(['waiting_for_info']),
                    or_(
                        Nodes.ip_address.in_(node_any_list),
                        Nodes.ocid.in_(node_any_list),
                        Nodes.serial.in_(node_any_list),
                        Nodes.hostname.in_(node_any_list),
                        Nodes.oci_name.in_(node_any_list)
                    ) 
                )
            ).all()  
        else:
            nodes_waiting_for_info = session.query(Nodes).filter(Nodes.controller_status.in_(['waiting_for_info'])).all()            
        for node in nodes_waiting_for_info:
            started_time = datetime.strptime(node.started_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if started_time < time_th:
                nodes_failing_to_start.append(node)
        return nodes_failing_to_start
    finally:
        session.close()

def get_all_nodes_unreachable(unreachable_timeout,node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    session = query_db()
    unreachable_nodes=[]
    current_time = datetime.now(UTC) if version >= (3, 12) else datetime.utcnow()
    time_th = (current_time - unreachable_timeout).replace(tzinfo=timezone.utc)
    try:
        if node_any_list:
            configured_nodes = session.query(Nodes).filter(
                and_(
                    and_(
                    Nodes.controller_status.in_(["configured"]),
                    Nodes.compute_status.in_(["configured", "configuring"])
                    ),
                    or_(
                        Nodes.ip_address.in_(node_any_list),
                        Nodes.ocid.in_(node_any_list),
                        Nodes.serial.in_(node_any_list),
                        Nodes.hostname.in_(node_any_list),
                        Nodes.oci_name.in_(node_any_list)
                    ) 
                )
            ).all()
        else:
            configured_nodes = session.query(Nodes).filter(
                and_(
                Nodes.controller_status.in_(["configured"]),
                Nodes.compute_status.in_(["configured", "configuring"])
                )
            ).all()
        for node in configured_nodes:
            last_time_reachable = datetime.strptime(node.last_time_reachable, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if last_time_reachable < time_th:
                unreachable_nodes.append(node)
        return unreachable_nodes
    finally:
        session.close()

def get_all_nodes_with_hc_status(hc_status,node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    session = query_db()
    try:
        if node_any_list:
            nodes = session.query(Nodes).filter(
                and_(
                    Nodes.healthcheck_recommendation == hc_status,
                    or_(
                        Nodes.ip_address.in_(node_any_list),
                        Nodes.ocid.in_(node_any_list),
                        Nodes.serial.in_(node_any_list),
                        Nodes.hostname.in_(node_any_list),
                        Nodes.oci_name.in_(node_any_list)
                    ) 
                )
            ).all()
        else:
            nodes = session.query(Nodes).filter(Nodes.healthcheck_recommendation == hc_status).all()
        return nodes
    finally:
        session.close()

def get_nodes_by_id(node_id_list):
    """Get a specific node by ID"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.ocid.in_(node_id_list)).all()
        return nodes
    finally:
        session.close()
    
def get_nodes_by_ip(node_ip_list):
    """Get a specific node by ID"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.ip_address.in_(node_ip_list)).all()
        return nodes
    finally:
        session.close()

def get_nodes_by_serial(node_serial_list):
    """Get a specific node by ID"""

    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.serial.in_(node_serial_list)).all()
        return nodes
    finally:
        session.close()
        
def get_nodes_by_name(node_name_list):
    """Get a specific node by hostname"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.hostname.in_(node_name_list)).all()
        return nodes
    finally:
        session.close()
    
def get_nodes_by_any(node_any_list):
    """Get a specific node by ID"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(or_(
            Nodes.ip_address.in_(node_any_list),
            Nodes.ocid.in_(node_any_list),
            Nodes.serial.in_(node_any_list),
            Nodes.hostname.in_(node_any_list),
            Nodes.oci_name.in_(node_any_list)
            )
        ).all()
        return nodes
    finally:
        session.close()

def get_running_nodes():
    """Get all nodes with 'running' status"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.status == 'running').all()
        return nodes
    finally:
        session.close()

def get_nodes_by_cluster(cluster_name):
    """Get all nodes belonging to a specific cluster"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.cluster_name == cluster_name).filter(
            or_(
                ~Nodes.role.in_(["controller","login"]),
                Nodes.role == None
            )
        ).all()
        return nodes
    finally:
        session.close()
        
def get_nodes_by_memory_cluster(cluster_name):
    """Get all nodes belonging to a specific cluster"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.memory_cluster_name == cluster_name).filter(
            or_(
                ~Nodes.role.in_(["controller","login"]),
                Nodes.role == None
            )
        ).all()
        return nodes
    finally:
        session.close()
        
def get_nodes_by_status(status):
    """Get all nodes with a specific status"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.status == status).all()
        return nodes
    finally:
        session.close()
        
def get_nodes_by_shape(shape):
    """Get all nodes with a specific shape"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.shape == shape).all()
        return nodes
    finally:
        session.close()
        
def get_nodes_by_hpc_island(hpc_island):
    """Get all nodes with a specific hpc_island"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.hpc_island == hpc_island).all()
        return nodes
    finally:
        session.close()
        
def get_nodes_by_network_block(network_block):
    """Get all nodes with a specific network block"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.network_block_id == network_block).all()
        return nodes
    finally:
        session.close()
        
def get_nodes_by_rail(rail_id):
    """Get all nodes with a specific rail ID"""
    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.rail_id == rail_id).all()
        return nodes
    finally:
        session.close()
        
def list_rails():
    """List all unique rail IDs"""
    session = query_db()
    try:
        rails = session.query(Nodes.rail_id).distinct().all()
        return [rail[0] for rail in rails]
    finally:
        session.close()

def list_blocks_by_cluster(cluster_name):
    """List all unique network blocks for a specific cluster"""
    session = query_db()
    try:
        blocks = session.query(Nodes.network_block_id).filter(Nodes.cluster_name == cluster_name).distinct().all()
        return [block[0] for block in blocks]
    finally:
        session.close()

def list_rails_by_cluster(cluster_name):
    """List all unique rail IDs for a specific cluster"""
    session = query_db()
    try:
        rails = session.query(Nodes.rail_id).filter(Nodes.cluster_name == cluster_name).distinct().all()
        return [rail[0] for rail in rails]
    finally:
        session.close()

def get_clusters():
    """List all unique clusternames"""
    session = query_db()
    try:
        cluster_names = session.query(Nodes.cluster_name).distinct().all()
        return [cluster_name[0] for cluster_name in cluster_names]
    finally:
        session.close()

def db_update_node(node, **kwargs):
    """
    Update fields for a node in the database identified by its OCID.

    Args:
        ocid (str): The OCID of the node to update.
        **kwargs: Field names and values to update.

    Example:
        db_update_node("ocid1.node.oc1..abc", status="running", controller_status="configured")
    """
    session = query_db()
    node = session.merge(node)
    try:
        for key, value in kwargs.items():
            if hasattr(node, key):
                setattr(node, key, value)
            else:
                logger.warning(f"Unknown attribute '{key}' ignored.")

        session.commit()
        logger.info(f"Node with OCID {node.ocid} updated")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating node {node.ocid}: {e}")
        return False
    finally:
        session.close()

def db_create_node(node_ocid, **kwargs):
    """
    Create node with the fields if the node does not exists.

    Args:
        **kwargs: Field names and values to update.

    Example:
        db_create_node("ocid1.node.oc1..abc", status="running", controller_status="configured")
    """
    session = query_db()
    try:
        node = session.query(Nodes).filter(Nodes.ocid == node_ocid).first()
        if node:
            logger.info(f"Node with OCID {node_ocid} found, updating...")
        else:
            logger.info(f"Node with OCID {node_ocid} not found, creating new node...")
            node = Nodes(ocid=node_ocid)
            session.add(node)

        for key, value in kwargs.items():
            if key != "ocid":
                if hasattr(node, key):
                    setattr(node, key, value)
                else:
                    logger.warning(f"Unknown attribute '{key}' ignored.")

        session.commit()
        logger.info(f"Node with OCID {node_ocid} upserted with {kwargs}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error upserting node {node_ocid}: {e}")
        return False
    finally:
        session.close()

def db_move_terminated_node(node):
    session = query_db()

    try:
        # Get shared column names, excluding 'id'
        source_columns = {c.key for c in inspect(Nodes).mapper.column_attrs}
        target_columns = {c.key for c in inspect(TerminatedNodes).mapper.column_attrs}
        shared_columns = source_columns & target_columns - {'id'}

        # Build the new TerminatedNodes object
        node_data = {col: getattr(node, col) for col in shared_columns}
        terminated_node = TerminatedNodes(**node_data)

        # Add to terminated table and delete from original
        session.add(terminated_node)
        session.delete(node)
        session.commit()

        logger.info(f"Node with OCID {node.ocid} moved to TerminatedNodes.")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error while moving node with OCID {node_ocid}: {e}")
        return False
    finally:
        session.close()

def db_duplicate_configuration(old_configuration_name,new_configuration_name):
    session = query_db()
    try:
        # Fetch the original configuration
        original = session.query(Configurations).filter(Configurations.name == old_configuration_name).first()

        if not original:
            logger.warning(f"No configuration found with name: {old_configuration_name}")
            return False

        # Prepare attribute dictionary (exclude 'id' and 'name')
        columns = {c.key for c in inspect(Configurations).mapper.column_attrs} - {'id', 'name'}
        data = {col: getattr(original, col) for col in columns}
        data['name'] = new_configuration_name  # set new name

        # Create and add the new configuration
        new_config = Configurations(**data)
        session.add(new_config)
        session.commit()

        logger.info(f"Configuration '{old_configuration_name}' duplicated as '{new_configuration_name}'")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error duplicating configuration: {e}")
        return False
    finally:
        session.close()

def db_update_configuration(configuration_name, **kwargs):
    """
    Update fields for a node in the database identified by its name.

    Args:
        ocid (str): The name of the configuration to update.
        **kwargs: Field names and values to update.

    Example:
        update_configuration("hpc-default", shape="BM.GPU.H100.8", image="ocid1.node.oc1..abc")
    """
    session = query_db()
    try:
        configuration = session.query(Configurations).filter(Configurations.name == configuration_name).first()
        if not configuration:
            logger.warning(f"No node found with OCID: {configuration_name}")
            return False

        for key, value in kwargs.items():
            if hasattr(configuration, key):
                setattr(configuration, key, value)
            else:
                logger.warning(f"Unknown attribute '{key}' ignored.")

        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating node {configuration_name}: {e}")
        return False
    finally:
        session.close()

def db_delete_configuration(configuration_name):
    """
    Delete Configuration
    Args:
        name (str): The name of the configuration to update.
    """
    session = query_db()
    try:
        configuration = session.query(Configurations).filter(Configurations.name == configuration_name).first()
        if not configuration:
            logger.warning(f"No node found with OCID: {configuration_name}")
            return False
        session.delete(configuration)
        session.commit()
        logger.info(f"Deleted configuration with name {configuration_name}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error deleting configuration {configuration_name}: {e}")
        return False
    finally:
        session.close()

def db_import_configuration(filename):
    session = query_db()
    try:
        with open(filename, 'r') as file:
            yaml_data = yaml.safe_load(file)

        queues = yaml_data.get("queues", [])
        for queue in queues:
            instance_types = queue.get("instance_types", [])
            for instance in instance_types:
                # Map YAML keys to SQLAlchemy model fields
                config = Configurations(
                    name=instance.get("name"),
                    partition=queue.get("name"),  # using queue name as partition
                    shape=instance.get("shape"),
                    change_hostname=instance.get("change_hostname", True),
                    hostname_convention=instance.get("hostname_convention"),
                    permanent=instance.get("permanent", True),
                    rdma_enabled=instance.get("rdma_enabled", True),
                    stand_alone=instance.get("stand_alone", False),
                    region=instance.get("region"),
                    ad=instance.get("ad"),
                    private_subnet_cidr=instance.get("private_subnet"),
                    private_subnet_id=instance.get("private_subnet_id"),
                    image=instance.get("image"),
                    target_compartment_id=instance.get("target_compartment_id"),
                    boot_volume_size=instance.get("boot_volume_size", 50),
                    use_marketplace_image=instance.get("use_marketplace_image", True),
                    instance_pool_ocpus=instance.get("instance_pool_ocpus"),
                    instance_pool_custom_memory=instance.get("instance_pool_custom_memory", False),
                    instance_pool_memory=instance.get("instance_pool_memory"),
                    marketplace_listing=instance.get("marketplace_listing"),
                    hyperthreading=instance.get("hyperthreading", True),
                    preemptible=instance.get("preemptible", False)
                )

                # Check if config already exists
                existing = session.query(Configurations).filter_by(name=config.name).first()
                if existing:
                    logger.info(f"Configuration '{config.name}' already exists. Skipping.")
                    continue

                session.add(config)

        session.commit()
        logger.info("All configurations successfully imported.")

    except Exception as e:
        logger.error(f"Error importing configurations: {e}")
        session.rollback()
    finally:
        session.close()


def get_config_by_name(name):
    """Show details about the configuration"""
    session = query_db()
    try:
        config = session.query(Configurations).filter(Configurations.name == name).first()
        return config
    finally:
        session.close()

def get_all_configs():
    """Show details about the configuration"""
    session = query_db()
    try:
        configs = session.query(Configurations).all()
        return configs
    finally:
        session.close()

def get_config_by_partition(partition):
    """Show details about the configuration"""
    session = query_db()
    try:
        configs = session.query(Configurations).filter(Configurations.partition == partition).all()
        return configs
    finally:
        session.close()

def get_config_by_shape(shape):
    """Show details about the configuration"""
    session = query_db()
    try:
        configs = session.query(Configurations).filter(Configurations.shape == shape).all()
        return configs
    finally:
        session.close()

def get_config_by_shape_and_partition(shape,partition):
    """Show details about the configuration"""
    session = query_db()
    try:
        configs = session.query(Configurations).filter(
            and_(Configurations.shape == shape,
                 Configurations.partition == partition
                 )
            ).all()
        return configs
    finally:
        session.close()