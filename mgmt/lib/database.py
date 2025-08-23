import logging
import os
import sys
import time

from datetime import datetime, timezone
from functools import cached_property
from typing import Optional

import sqlalchemy
import yaml

from sqlalchemy import (
    Integer, String, Boolean, Enum, or_, and_, not_,
    create_engine, select
)

from sqlalchemy.orm import mapped_column, sessionmaker, DeclarativeBase
from sqlalchemy.inspection import inspect
from sqlalchemy.dialects.mysql import INTEGER

from ClusterShell.NodeSet import NodeSet

# pylint: disable=logging-fstring-interpolation
# pylint: disable=missing-function-docstring

# This is expected with "Base" subclasses
# pylint: disable=too-few-public-methods


MYSQL_CONNECTION_DETAILS = {
    "db_host": "localhost",
    "db_user": "clusterUser",
    "db_pw": "Cluster1234!",
    "db_name": "clusterDB",
}

UnsignedInt = Integer().with_variant(INTEGER(unsigned=True), 'mysql')


class Base(DeclarativeBase):
    pass


class NodesMixin:
    """
    Base definition of a "nodes" table.

    The actual Nodes and TerminatedNodes classes will only need to include the
    columns that differ between them.
    """

    id                         = mapped_column(UnsignedInt, primary_key=True, autoincrement=True)
    controller_status          = mapped_column(Enum(
        'configuring', 'terminating', 'waiting_for_info', 'configured', 'terminated', 'reconfiguring'
    ), nullable=True)
    started_time               = mapped_column(String(128), nullable=True)
    status                     = mapped_column(Enum(
        'starting', 'terminating', 'terminated', 'running', 'unreachable'
    ), nullable=True)
    availability_domain        = mapped_column(String(128), nullable=True)
    first_time_reachable       = mapped_column(String(128), nullable=True)
    cluster_name               = mapped_column(String(128), nullable=True)
    compartment_id             = mapped_column(String(128), nullable=True)
    tenancy_id                 = mapped_column(String(128), nullable=True)
    compute_status             = mapped_column(Enum(
        'configuring', 'configured', 'starting', 'terminating'
    ), nullable=True)
    controller_name            = mapped_column(String(128), nullable=True)
    fss_mount                  = mapped_column(String(128), nullable=True)
    gpu_memory_fabric          = mapped_column(String(128), nullable=True)
    hpc_island                 = mapped_column(String(128), nullable=True)
    image_id                   = mapped_column(String(128), nullable=True)
    last_time_reachable        = mapped_column(String(128), nullable=True)
    oci_name                   = mapped_column(String(128), nullable=True)
    ocid                       = mapped_column(String(128), unique=True, nullable=True)
    rack_id                    = mapped_column(String(128), nullable=True)
    rail_id                    = mapped_column(String(128), nullable=True)
    network_block_id           = mapped_column(String(128), nullable=True)
    memory_cluster_name        = mapped_column(String(128), nullable=True)
    role                       = mapped_column(String(128), nullable=True)
    shape                      = mapped_column(String(128), nullable=True)
    terminated_time            = mapped_column(String(128), nullable=True)
    update_count               = mapped_column(Integer, nullable=True)
    passive_healthcheck_recommendation = mapped_column(String(128), nullable=True)
    passive_healthcheck_time   = mapped_column(String(128), nullable=True)
    passive_healthcheck_logs   = mapped_column(String(2048), nullable=True)
    active_healthcheck_time    = mapped_column(String(128), nullable=True)
    active_healthcheck_logs    = mapped_column(String(2048), nullable=True)
    active_healthcheck_recommendation = mapped_column(String(128), nullable=True)
    multi_node_HC_time         = mapped_column(String(128), nullable=True)
    multi_node_HC_logs         = mapped_column(String(2048), nullable=True)
    multi_node_HC_recommendation = mapped_column(String(128), nullable=True)
    multi_node_HC_node         = mapped_column(String(128), nullable=True)
    oci_health                 = mapped_column(String(128), nullable=True)
    oci_impacted_components    = mapped_column(Boolean, default=False, nullable=True)
    oci_host_id                = mapped_column(String(128), nullable=True)


class Nodes(NodesMixin, Base):
    __tablename__ = 'nodes'

    ip_address = mapped_column(String(128), unique=True, nullable=True)
    hostname   = mapped_column(String(128), unique=True, nullable=True)
    serial     = mapped_column(String(128), unique=True, nullable=True)


class TerminatedNodes(NodesMixin, Base):
    __tablename__ = 'terminated_nodes'

    ip_address = mapped_column(String(128), nullable=True)
    hostname   = mapped_column(String(128), nullable=True)
    serial     = mapped_column(String(128), nullable=True)


class Configurations(Base):
    __tablename__ = 'configurations'

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    name = mapped_column(String(64), unique=True, nullable=False)
    partition = mapped_column(String(64), nullable=False)
    shape = mapped_column(String(64), nullable=False)
    change_hostname = mapped_column(Boolean, default=True, nullable=False)
    hostname_convention = mapped_column(String(64), nullable=True)
    permanent = mapped_column(Boolean, default=True, nullable=False)
    rdma_enabled = mapped_column(Boolean, default=True, nullable=False)
    stand_alone = mapped_column(Boolean, default=False, nullable=False)
    region = mapped_column(String(64), nullable=True)
    availability_domain = mapped_column(String(64), nullable=True)
    private_subnet_cidr = mapped_column(String(64), nullable=True)
    private_subnet_id = mapped_column(String(128), nullable=True)
    image_id = mapped_column(String(128), nullable=True)
    target_compartment_id = mapped_column(String(128), nullable=True)
    boot_volume_size = mapped_column(Integer, nullable=True)
    use_marketplace_image = mapped_column(Boolean, default=False, nullable=False)
    instance_pool_ocpus = mapped_column(Integer, nullable=True)
    instance_pool_custom_memory = mapped_column(Boolean, default=False, nullable=False)
    instance_pool_memory = mapped_column(Integer, nullable=True)
    marketplace_listing = mapped_column(String(64), nullable=True)
    hyperthreading = mapped_column(Boolean, default=True, nullable=False)
    preemptible = mapped_column(Boolean, default=False, nullable=False)


logger = logging.getLogger(__name__)


class DBConn:
    """
    Experimental class to see if it makes sense to have a centralized session
    creator and context manager. I'm not quite happy with this design.
    """

    def __init__(self, connection_string=None):
        self.session = None

        connection_string = os.environ.get("DB_CONNECTION_STRING", connection_string)

        if not connection_string:
            connection_string = "mysql+pymysql://{db_user}:{db_pw}@{db_host}/{db_name}".format_map(
                MYSQL_CONNECTION_DETAILS
            )

        self.connection_string = connection_string

    @cached_property
    def engine(self):
        # Create the SQLAlchemy engine
        return create_engine(self.connection_string)

    def __enter__(self):
        if self.session is None:
            Session = sessionmaker(bind=self.engine)
            self.session = Session()

        return self.session

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is not None:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None


def db_create():
    conn = DBConn()
    Base.metadata.create_all(conn.engine)


def db_export(outfile="export.sqlite", use_base_metadata=True):
    """
    Export the source database to a sqlite database. This is very simplistic
    code and does no validation that the source db has the right
    tables/columns, nor does it check whether the target already exists.
    """

    engine_db = DBConn().engine
    engine_sqlite = create_engine(f"sqlite:///{outfile}")

    if use_base_metadata:
        metadata_obj = Base.metadata
    else:
        metadata_obj = sqlalchemy.MetaData()
        metadata_obj.reflect(bind=engine_db)

    metadata_obj.create_all(engine_sqlite)

    with engine_db.connect() as conn_db, engine_sqlite.connect() as conn_sqlite:
        for table in metadata_obj.sorted_tables:
            for row in conn_db.execute(select(table.c)):
                conn_sqlite.execute(table.insert().values(row._mapping))
            conn_sqlite.commit()


def current_utc_time():
    if sys.version_info >= (3, 12):
        now = datetime.now(timezone.utc)
    else:
        now = datetime.utcnow()

    return now


def query_db():
    connection_string = os.environ.get("DB_CONNECTION_STRING")
    if not connection_string:
        connection_string = "mysql+pymysql://{db_user}:{db_pw}@{db_host}/{db_name}".format_map(
            MYSQL_CONNECTION_DETAILS
        )

    try:
        # Create the SQLAlchemy engine
        engine = create_engine(connection_string)

        # Create a session factory
        Session = sessionmaker(bind=engine)
        session = Session()

        return session
    except Exception as exc:
        logger.error(f"Error connecting to the database: {exc}")
        sys.exit(1)


def node_to_dict(node, keys=None):
    return {
        c.key: getattr(node, c.key)
        for c in inspect(node).mapper.column_attrs
        if keys is None or c.key in keys
    }


def field_to_rich_renderable(val):
    """
    Convert db data into types "renderable" in Rich tables.

    Works on a very limited set of data types and would need to be extended as
    new types are used.
    """

    if val is None:
        return ""

    # `bool` is a subclass of `int` so this comes before the `int` check
    if isinstance(val, bool):
        return str(val)

    if isinstance(val, (int, str)):
        return val

    # At the time of writing, this type wasn't used. Not sure why I included
    # this. It's untested.
    if isinstance(val, bytes):
        return bytes.decode("utf-8")

    # Unrecognized type. YOLO!
    return val


def node_to_list(node, columns=None):
    return [
        field_to_rich_renderable(getattr(node, col))
        for col in columns
    ]


def list_columns(table="nodes"):
    return [col for col in Base.metadata.tables[table].columns.keys() if col != "id"]


def filter_nodes(session, query=None, filter="all"):
    """
    Experimenting with an approach to have a "query" which can be passed to
    multiple functions and refined as we go.

    This is just the start of an idea as a drop-in replacement for some of the
    existing `get_*_nodes` methods.
    """

    if query is None:
        if filter == "terminated":
            query = session.query(TerminatedNodes)
        else:
            query = session.query(Nodes).filter(Nodes.status != "terminated")

    if filter == "all":
        pass
    elif filter == "compute":
        query = query.filter(Nodes.role == "compute")
    elif filter == "management":
        query = query.filter(Nodes.role != "compute")
    elif filter == "controller":
        query = query.filter(Nodes.role == "controller")

    return query


def filter_nodes_by_cluster(query, cluster_name=None, memory_cluster_name=None):
    if cluster_name is not None:
        query = query.filter(
            Nodes.cluster_name == cluster_name
        )
    elif memory_cluster_name is not None:
        query = query.filter(
            Nodes.memory_cluster_name == memory_cluster_name
        )
    else:
        # NoOP. This allows the function to be called unconditionally and only
        # filter data is one of the cluster name args is passed in.
        return query

    query = query.filter(
        or_(
            ~Nodes.role.in_(["controller", "login"]),
            Nodes.role.is_(None)
        )
    )

    return query


def get_all_nodes():
    """Get all nodes/servers from the database"""
    with DBConn() as session:
        return filter_nodes(session, filter="all").all()


def get_all_compute_nodes():
    """Get all nodes/servers from the database"""
    with DBConn() as session:
        return filter_nodes(session, filter="compute").all()


def get_all_management_nodes():
    """Get all nodes/servers from the database"""
    with DBConn() as session:
        return filter_nodes(session, filter="management").all()


def get_controller_node():
    """Get the controller from the database"""
    with DBConn() as session:
        return filter_nodes(session, filter="controller").first()


def get_all_terminated_nodes():
    """Get all nodes/servers from the database"""
    with DBConn() as session:
        return filter_nodes(session, filter="terminated").all()


def get_all_nodes_to_configure():
    """Get all nodes/servers from the database"""
    session = query_db()
    try:
        nodes_configuring = session.query(Nodes).filter(
            and_(
                Nodes.controller_status.in_(['configuring', 'reconfiguring']),
                Nodes.compute_status.in_(['configuring','configured'])
            )
        ).all()
        nodes_terminating = session.query(Nodes).filter(
                Nodes.controller_status == 'terminating'
        ).all()
        return nodes_configuring, nodes_terminating
    finally:
        session.close()


def get_all_nodes_failing_to_start(unreachable_timeout, node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    session = query_db()
    nodes_failing_to_start = []
    current_time = current_utc_time()
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
            nodes_waiting_for_info = session.query(Nodes).filter(
                    Nodes.controller_status.in_(['waiting_for_info'])
            ).all()

        for node in nodes_waiting_for_info:
            started_time = datetime.strptime(
                node.started_time, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            if started_time < time_th:
                nodes_failing_to_start.append(node)
        return nodes_failing_to_start
    finally:
        session.close()


def get_all_nodes_unreachable(unreachable_timeout, node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    session = query_db()
    unreachable_nodes = []
    current_time = current_utc_time()
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
            last_time_reachable = datetime.strptime(
                node.last_time_reachable, "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)

            if last_time_reachable < time_th:
                unreachable_nodes.append(node)
        return unreachable_nodes
    finally:
        session.close()


def get_all_nodes_with_hc_status(hc_status, node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    session = query_db()
    try:
        if node_any_list:
            nodes = session.query(Nodes).filter(
                and_(
                    Nodes.passive_healthcheck_recommendation == hc_status,
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
            nodes = session.query(Nodes).filter(Nodes.passive_healthcheck_recommendation == hc_status).all()
        return nodes
    finally:
        session.close()


def get_nodes_by_id(node_id_list):
    """Get a specific node by ID"""

    if isinstance(node_id_list, str):
        node_id_list = NodeSet(node_id_list)

    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.ocid.in_(node_id_list)).all()
        return nodes
    finally:
        session.close()


def get_nodes_by_ip(node_ip_list):
    """Get a specific node by ID"""

    if isinstance(node_ip_list, str):
        node_ip_list = NodeSet(node_ip_list)

    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.ip_address.in_(node_ip_list)).all()
        return nodes
    finally:
        session.close()


def get_nodes_by_serial(node_serial_list):
    """Get a specific node by ID"""

    if isinstance(node_serial_list, str):
        node_serial_list = NodeSet(node_serial_list)

    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.serial.in_(node_serial_list)).all()
        return nodes
    finally:
        session.close()


def get_nodes_by_name(node_name_list):
    """Get a specific node by hostname"""

    if isinstance(node_name_list, str):
        node_name_list = NodeSet(node_name_list)

    session = query_db()
    try:
        nodes = session.query(Nodes).filter(Nodes.hostname.in_(node_name_list)).all()
        return nodes
    finally:
        session.close()


def get_nodes_by_any(node_any_list):
    """Get a specific node by ID"""

    if isinstance(node_any_list, str):
        node_any_list = NodeSet(node_any_list)

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
                ~Nodes.role.in_(["controller", "login"]),
                Nodes.role.is_(None)
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
                ~Nodes.role.in_(["controller", "login"]),
                Nodes.role.is_(None)
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

def get_nodes_by_filters(filters_dict):
    """Get all nodes matching the provided filters.
    
    Args:
        filters_dict (dict): Dictionary where keys are column names and values are the filter values.
                            Example: {'status': 'active', 'shape': 'VM.Standard2.1'}
    Returns:
        list: List of Nodes objects matching all the provided filters.
    """
    if not filters_dict:
        return []
        
    session = query_db()
    try:
        query = session.query(Nodes)
        for column, value in filters_dict.items():
            if hasattr(Nodes, column):
                query = query.filter(getattr(Nodes, column) == value)
        return query.all()
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
        blocks = session.query(Nodes.network_block_id).filter(
                Nodes.cluster_name == cluster_name
        ).distinct().all()

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
        return True 
    except Exception as exc:
        logger.error(f"Error updating node {node.ocid}: {exc}")
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
                    logger.debug(
                        "Available attributes: %s | Tried to set: %s=%s",
                        [attr for attr in dir(node) if not attr.startswith("_")],
                        key,
                        value,
                    )
        session.commit()
        logger.info(f"Node with OCID {node_ocid} upserted with {kwargs}")
        return True
    except Exception as exc:
        session.rollback()
        logger.error(f"Error upserting node {node_ocid}: {exc}")
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
        logger.debug(f"Node with OCID {node.ocid} added to TerminatedNodes.")
        logger.debug(f"Node with OCID {node.ocid} removed from Nodes.")

        test_nodes = session.query(Nodes).filter(Nodes.ocid == node.ocid).all()
        for test_node in test_nodes:
            logger.debug(f"Node with OCID {test_node.ocid} is still in the DB.")
        return True
    except Exception as exc:
        session.rollback()
        logger.error(f"Error while moving node with OCID {node.ocid}: {exc}")
        return False
    finally:
        session.close()


def db_duplicate_configuration(old_configuration_name, new_configuration_name):
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
    except Exception as exc:
        session.rollback()
        logger.error(f"Error duplicating configuration: {exc}")
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
        configuration = session.query(Configurations).filter(
                Configurations.name == configuration_name
        ).first()

        if not configuration:
            logger.warning(f"No node found with OCID: {configuration_name}")
            return False

        for key, value in kwargs.items():
            if hasattr(configuration, key):
                setattr(configuration, key, value)
            else:
                logger.warning(f"Unknown attribute '{key}' ignored.")

        time.sleep(1)
        session.commit()
        return True
    except Exception as exc:
        logger.error(f"Error updating node {configuration_name}: {exc}")
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
        configuration = session.query(Configurations).filter(
                Configurations.name == configuration_name
        ).first()

        if not configuration:
            logger.warning(f"No node found with OCID: {configuration_name}")
            return False
        session.delete(configuration)
        session.commit()
        logger.info(f"Deleted configuration with name {configuration_name}")
        return True
    except Exception as exc:
        session.rollback()
        logger.error(f"Error deleting configuration {configuration_name}: {exc}")
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
                    availability_domain=instance.get("availability_domain"),
                    private_subnet_cidr=instance.get("private_subnet"),
                    private_subnet_id=instance.get("private_subnet_id"),
                    image_id=instance.get("image_id"),
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

    except Exception as exc:
        logger.error(f"Error importing configurations: {exc}")
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


def get_config_by_shape_and_partition(shape, partition):
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

def db_delete_node(node):
    session = query_db()
    try:
        session.delete(node)
        session.commit()
    finally:
        session.close()
    