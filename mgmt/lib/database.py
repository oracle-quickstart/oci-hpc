import logging
import os
import sys
import time

from datetime import datetime, timezone, timedelta
from functools import cached_property
from typing import Optional

import sqlalchemy
import yaml

from sqlalchemy import (
    Integer, String, Boolean, Enum, or_, and_, not_, true, 
    create_engine, select, func, case, cast, DateTime, text
)
from sqlalchemy.orm import mapped_column, sessionmaker, DeclarativeBase, aliased
from sqlalchemy.inspection import inspect
from sqlalchemy.dialects.mysql import INTEGER
from sqlalchemy.engine.row import Row

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
    instance_type              = mapped_column(String(128), nullable=True)
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
    slurm_state                = mapped_column(String(128), nullable=True)
    slurm_partition            = mapped_column(String(128), nullable=True)
    slurm_reservation          = mapped_column(String(128), nullable=True)
    slurm_up_time              = mapped_column(Integer, nullable=True)
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
    role = mapped_column(Enum('compute', 'login'), nullable=False)
    partition = mapped_column(String(64), nullable=False)
    default_partition = mapped_column(Boolean, default=True, nullable=False)
    shape = mapped_column(String(64), nullable=False)
    change_hostname = mapped_column(Boolean, default=True, nullable=False)
    hostname_convention = mapped_column(String(64), nullable=True)
    permanent = mapped_column(Boolean, default=True, nullable=False)
    rdma_enabled = mapped_column(Boolean, default=True, nullable=False)
    stand_alone = mapped_column(Boolean, default=False, nullable=False)
    max_number_nodes = mapped_column(Integer, nullable=True)
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

class HealthChecks(Base):
    __tablename__ = 'healthchecks'

    id = mapped_column(Integer, primary_key=True, autoincrement=True)
    ocid = mapped_column(String(128), nullable=False)
    healthcheck_type = mapped_column(String(64), nullable=False)
    healthcheck_logs = mapped_column(String(4096), nullable=True)
    healthcheck_time_change = mapped_column(String(128), nullable=True)
    healthcheck_last_time = mapped_column(String(128), nullable=True)
    healthcheck_recommendation = mapped_column(String(128), nullable=True)
    healthcheck_status = mapped_column(String(128), nullable=True)
    healthcheck_associated_node = mapped_column(String(128), nullable=True)

    
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

def get_extra_columns_per_hc():
    return ["healthcheck_status", "healthcheck_logs", "healthcheck_recommendation", "healthcheck_last_time","healthcheck_associated_node"]

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


# def node_to_dict(node, keys=None):

#     dict_all={
#         c.key: getattr(node, c.key)
#         for c in inspect(node).mapper.column_attrs
#         if keys is None or c.key in keys
#     }
#     return_dict={}
#     if keys is not None:
#         for key in sorted(keys):
#             return_dict[key]=dict_all[key]
#     else:
#         for key in sorted(dict_all.keys()):
#             return_dict[key]=dict_all[key]
#     return return_dict

def node_to_dict(node, keys=None):
    """
    Convert a Node (ORM or Row) to a dict. 
    If it's a Row, we use its _mapping. 
    If it's an ORM, we fall back to getattr().
    """
    result = {}

    if hasattr(node, "_mapping"):  # Row object
        mapping = dict(node._mapping)
        if keys:
            for key in sorted(keys):
                result[key] = mapping.get(key)
        else:
            for key in sorted(mapping.keys()):
                result[key] = mapping[key]

    else:  # ORM-mapped Node
        all_attrs = {c.key: getattr(node, c.key) for c in inspect(node).mapper.column_attrs}
        if keys:
            for key in sorted(keys):
                result[key] = all_attrs.get(key)
        else:
            for key in sorted(all_attrs.keys()):
                result[key] = all_attrs[key]

    return result

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
        
    result = []
    values={}
    for col in columns:
        result.append(field_to_rich_renderable(getattr(node, col, None)))                    
    return result

def list_columns():
    query=get_nodes_with_latest_healthchecks()
    return [col['name'] for col in query.column_descriptions if col['name'] != "id"]

def get_nodes_with_latest_healthchecks():
    """
    Return a SQLAlchemy query for Node ORM objects with aggregated healthcheck columns:
    active, passive, multi-node status, logs, recommendations, last_time, etc.
    """
    with DBConn() as session:
        hc = aliased(HealthChecks)

        # Subquery: latest healthcheck per (ocid, type)
        subq = (
            session.query(
                hc.ocid.label("node_ocid"),
                hc.healthcheck_type,
                hc.healthcheck_status,
                hc.healthcheck_logs,
                hc.healthcheck_recommendation,
                hc.healthcheck_associated_node,
                hc.healthcheck_last_time,
                func.row_number().over(
                    partition_by=[hc.ocid, hc.healthcheck_type],
                    order_by=hc.healthcheck_last_time.desc()
                ).label("rn")
            )
            .subquery()
        )

        # Aggregated columns
        agg_columns = []
        for hc_type in ["active", "passive", "multi-node"]:
            for c in get_extra_columns_per_hc():
                agg_columns.append(
                    func.max(
                        case(
                            (subq.c.healthcheck_type == hc_type, getattr(subq.c, c))
                        )
                    ).label(f"{hc_type.replace('-', '_')}_{c}")
                )

        # Build query and outer join to nodes
        query = (
            session.query(Nodes, *agg_columns)
            .outerjoin(subq, and_(Nodes.ocid == subq.c.node_ocid, subq.c.rn == 1))
            .group_by(Nodes.ocid)
        )

        # Wrap in subquery for global recommendation
        base_subq = query.subquery()

        query_with_global_rec = session.query(
            base_subq,
            case(
                (
                    base_subq.c.passive_healthcheck_recommendation != "Healthy",
                    base_subq.c.passive_healthcheck_recommendation,
                ),
                (
                    and_(
                        base_subq.c.active_healthcheck_recommendation.isnot(None),
                        base_subq.c.active_healthcheck_recommendation != "",
                        base_subq.c.active_healthcheck_recommendation != "Healthy",
                    ),
                    base_subq.c.active_healthcheck_recommendation,
                ),
                (
                    and_(
                        base_subq.c.multi_node_healthcheck_recommendation.isnot(None),
                        base_subq.c.multi_node_healthcheck_recommendation != "",
                        base_subq.c.multi_node_healthcheck_recommendation != "Healthy",
                    ),
                    base_subq.c.multi_node_healthcheck_recommendation,
                ),
                else_=base_subq.c.passive_healthcheck_recommendation,
            ).label("healthcheck_recommendation"),
        )
        return query_with_global_rec

def get_terminated_nodes_with_latest_healthchecks(delay=None):
    """
    Return TERMINATED nodes with their latest aggregated healthchecks.

    This function intentionally mirrors get_nodes_with_latest_healthchecks(),
    but operates on the terminated node set. The logic is kept separate to
    avoid changing the behavior of the existing active-node query.
    """
    with DBConn() as session:
        hc = aliased(HealthChecks)

        subq = (
            session.query(
                hc.ocid.label("node_ocid"),
                hc.healthcheck_type,
                hc.healthcheck_status,
                hc.healthcheck_logs,
                hc.healthcheck_recommendation,
                hc.healthcheck_associated_node,
                hc.healthcheck_last_time,
                func.row_number().over(
                    partition_by=[hc.ocid, hc.healthcheck_type],
                    order_by=hc.healthcheck_last_time.desc()
                ).label("rn")
            )
            .subquery()
        )

        agg_columns = []
        for hc_type in ["active", "passive", "multi-node"]:
            for c in get_extra_columns_per_hc():
                agg_columns.append(
                    func.max(
                        case(
                            (subq.c.healthcheck_type == hc_type, getattr(subq.c, c))
                        )
                    ).label(f"{hc_type.replace('-', '_')}_{c}")
                )

        query = (
            session.query(TerminatedNodes, *agg_columns)
            .outerjoin(subq, and_(
                TerminatedNodes.ocid == subq.c.node_ocid,
                subq.c.rn == 1
            ))
            .group_by(TerminatedNodes.ocid)
        )
        if delay is not None:
            cutoff_time = datetime.now() - timedelta(minutes=int(delay))
            query = query.filter(
                cast(TerminatedNodes.terminated_time, DateTime) >= cutoff_time
            )
        base_subq = query.subquery()



        return session.query(
            base_subq,
            case(
                (
                    base_subq.c.passive_healthcheck_recommendation != "Healthy",
                    base_subq.c.passive_healthcheck_recommendation,
                ),
                (
                    and_(
                        base_subq.c.active_healthcheck_recommendation.isnot(None),
                        base_subq.c.active_healthcheck_recommendation != "",
                        base_subq.c.active_healthcheck_recommendation != "Healthy",
                    ),
                    base_subq.c.active_healthcheck_recommendation,
                ),
                (
                    and_(
                        base_subq.c.multi_node_healthcheck_recommendation.isnot(None),
                        base_subq.c.multi_node_healthcheck_recommendation != "",
                        base_subq.c.multi_node_healthcheck_recommendation != "Healthy",
                    ),
                    base_subq.c.multi_node_healthcheck_recommendation,
                ),
                else_=base_subq.c.passive_healthcheck_recommendation,
            ).label("healthcheck_recommendation"),
        )

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
    elif filter == "login":
        query = query.filter(Nodes.role == "login")

    return query



def get_query_by_fields(query, field_dict):
    """Get a query filtered by node fields and latest healthcheck results."""
    if not field_dict:
        return query

    col_names = {c['name'] for c in query.column_descriptions}

    try:
        for i, (key, value) in enumerate(field_dict.items()):
            param_name = f"value_{i}"  # unique param per filter

            if key == "healthcheck_recommendation":
                query = query.having(text(f"healthcheck_recommendation = :{param_name}")).params(**{param_name: value})
            elif key in col_names:
                query = query.filter(text(f"{key} = :{param_name}")).params(**{param_name: value})
            else:
                logger.warning(f"Invalid field name: {key}")

        return query

    except Exception as exc:
        logger.error(f"Error filtering nodes with fields {field_dict}: {exc}")
        raise

def join_nodes_lists(list1,list2):
    list1_ocids=[node.ocid for node in list1]
    list2_ocids=[node.ocid for node in list2]
    ocids=list(set(list1_ocids).union(set(list2_ocids)))
    node_list=[]
    for ocid in ocids:
        found=False
        for node1 in list1:
            if node1.ocid == ocid:
                node_list.append(node1)
                found=True
                break
        if not found:
            for node2 in list2:
                if node2.ocid == ocid:
                    node_list.append(node2)
                    found=True
                    break
    return node_list

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

def get_all_login_nodes():
    """Get all nodes/servers from the database"""
    with DBConn() as session:
        return filter_nodes(session, filter="login").all()

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
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes_failing_to_start = []
    current_time = current_utc_time()
    time_th = (current_time - unreachable_timeout).replace(tzinfo=timezone.utc)

    if node_any_list:
        nodes_waiting_for_info = query.filter(
            and_(
                label_map["controller_status"].in_(["waiting_for_info"]),
                or_(
                    label_map["ip_address"].in_(node_any_list),
                    label_map["ocid"].in_(node_any_list),
                    label_map["serial"].in_(node_any_list),
                    label_map["hostname"].in_(node_any_list),
                    label_map["oci_name"].in_(node_any_list)
                )
            )
        ).all()
    else:
        nodes_waiting_for_info = query.filter(label_map["controller_status"].in_(["waiting_for_info"])).all()
    for node in nodes_waiting_for_info:
        started_time = datetime.strptime(
            node.started_time, "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)

        if started_time < time_th:
            nodes_failing_to_start.append(node)
    return nodes_failing_to_start


def get_nodes_slurm_unconfigured():
    query = get_nodes_with_latest_healthchecks()
    field_dict = {"role":"compute","slurm_state":"unconfigured"}
    nodes_slurm_unconfigured = get_query_by_fields(query,field_dict).all()
    return nodes_slurm_unconfigured


def get_all_nodes_unreachable(unreachable_timeout, node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    unreachable_nodes = []
    current_time = current_utc_time()
    time_th = (current_time - unreachable_timeout).replace(tzinfo=timezone.utc)
    if node_any_list:
        configured_nodes = query.filter(
            and_(
                label_map["controller_status"].in_(["configured"]),
                or_(
                    label_map["ip_address"].in_(node_any_list),
                    label_map["ocid"].in_(node_any_list),
                    label_map["serial"].in_(node_any_list),
                    label_map["hostname"].in_(node_any_list),
                    label_map["oci_name"].in_(node_any_list)
                )
            )
        ).all()
    else:
        configured_nodes = query.filter(
            and_(
                label_map["controller_status"].in_(["configured"]),
                label_map["compute_status"].in_(["configured", "configuring"]) 
            )
        
        ).all()
    for node in configured_nodes:
        last_time_reachable = datetime.strptime(
            node.last_time_reachable, "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)

        if last_time_reachable < time_th:
            unreachable_nodes.append(node)
    return unreachable_nodes


def get_all_nodes_with_hc_status(hc_status, node_any_list):
    """Get all nodes/servers from the database in waiting_for_info status"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}

    if node_any_list:
        nodes = query.filter(
            and_(
                label_map["passive_healthcheck_recommendation"] == hc_status,
                or_(
                    label_map["ip_address"].in_(node_any_list),
                    label_map["ocid"].in_(node_any_list),
                    label_map["serial"].in_(node_any_list),
                    label_map["hostname"].in_(node_any_list),
                    label_map["oci_name"].in_(node_any_list)
                )
            )
        ).all()
    else:
        nodes = query.filter(label_map["passive_healthcheck_recommendation"] == hc_status).all()
    return nodes


def get_nodes_by_id(node_id_list):
    """Get a specific node by ID"""

    if isinstance(node_id_list, str):
        node_id_list = NodeSet(node_id_list)

    
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["ocid"].in_(node_id_list)).all()
    return nodes


def get_nodes_by_ip(node_ip_list):
    """Get a specific node by ID"""

    if isinstance(node_ip_list, str):
        node_ip_list = NodeSet(node_ip_list)

    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["ip_address"].in_(node_ip_list)).all()
    return nodes



def get_nodes_by_serial(node_serial_list):
    """Get a specific node by ID"""

    if isinstance(node_serial_list, str):
        node_serial_list = NodeSet(node_serial_list)

    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["serial"].in_(node_serial_list)).all()
    return nodes


def get_nodes_by_name(node_name_list):
    """Get a specific node by hostname"""

    if isinstance(node_name_list, str):
        node_name_list = NodeSet(node_name_list)

    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["hostname"].in_(node_name_list)).all()
    return nodes


def get_nodes_by_any(node_any_list):
    """Get a specific node by ID"""

    if isinstance(node_any_list, str):
        node_any_list = NodeSet(node_any_list)

    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(or_(
            label_map["ip_address"].in_(node_any_list),
            label_map["ocid"].in_(node_any_list),
            label_map["serial"].in_(node_any_list),
            label_map["hostname"].in_(node_any_list),
            label_map["oci_name"].in_(node_any_list)
            )
        ).all()
    return nodes


def get_running_nodes():
    """Get all nodes with 'running' status"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["status"] == 'running').all()
    return nodes


def get_nodes_by_cluster(cluster_name):
    """Get all nodes belonging to a specific cluster"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    query = query.filter(label_map["cluster_name"] == cluster_name)
    query = query.filter(
        or_(
            ~label_map["role"].in_(["controller", "login", "monitoring"]),
            label_map["role"].is_(None)
        )
    )
    nodes = query.all()
    return nodes


def get_nodes_by_memory_cluster(cluster_name):
    """Get all nodes belonging to a specific cluster"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    query = query.filter(label_map["memory_cluster_name"] == cluster_name)
    query = query.filter(
        or_(
            ~label_map["role"].in_(["controller", "login", "monitoring"]),
            label_map["role"].is_(None)
        )
    )
    nodes = query.all()
    return nodes

def get_nodes_by_active_hc_expired(active_hc_timeout):
    """Get all nodes whose active healthcheck is expired."""

    current_time = current_utc_time()
    time_th = current_time - active_hc_timeout
    
    initial_validation_timeout=timedelta(hours=1)
    initial_validation_time_th = (current_time - initial_validation_timeout)

    query = get_nodes_with_latest_healthchecks()

    # Build a label map for extra columns
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}

    # Debug counts
    query = query.filter(label_map["role"] == "compute")
    logger.debug(f"Count after role filter: {query.count()}")
    query = query.filter(label_map["shape"].in_([
        "BM.GPU.H100.8", "BM.GPU.A100-v2.8", "BM.GPU4.8",
        "BM.GPU.B4.8", "BM.GPU.H200.8", "BM.GPU.GB200.4", "BM.GPU.B200.8", "BM.GPU.GB200-v2.4", "BM.GPU.GB200-v3.4", "BM.GPU.GB300.4", "BM.GPU.MI355X.8", "BM.GPU.MI355X-v1.8", "BM.GPU.MI355X-v0.8"
    ]))
    logger.debug(f"Count after shape filter: {query.count()}")
    idle_query = query.filter(label_map["slurm_state"] == "idle")
    logger.debug(f"Count after slurm state filter: {idle_query.count()}")
    idle_query = idle_query.filter(label_map["passive_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after passive healthcheck filter: {idle_query.count()}")
    idle_query= idle_query.filter(label_map.get("slurm_up_time") > 300)
    logger.debug(f"Count after slurm uptime check ( > 5minutes): {idle_query.count()}")
    # Add having for expired active healthcheck
    col = label_map.get("active_healthcheck_last_time")
    if col is not None:
        idle_query= idle_query.filter(
            or_(
                col == None,  # NULL treated as expired
                cast(col, DateTime) < time_th
            )
        )
    logger.debug(f"Count after expired active healthcheck filter: {idle_query.count()}")
    idle_result = idle_query.all()

    starting_nodes_query = query.filter(label_map["slurm_state"] == "resv")
    logger.debug(f"Count after slurm status check: {starting_nodes_query.count()}")
    starting_nodes_query = starting_nodes_query.filter(label_map["slurm_reservation"]=="InitialValidation")
    logger.debug(f"Count after slurm reservation name check : {starting_nodes_query.count()}")
    col = label_map.get("active_healthcheck_last_time")
    if col is not None:
        starting_nodes_query= starting_nodes_query.filter(
            or_(
                col == None,  # NULL treated as expired
                cast(col, DateTime) < initial_validation_time_th
            )
        )
    logger.debug(f"Count after slurm initial validation timeout check: {starting_nodes_query.count()}")
    starting_nodes_results = starting_nodes_query.all()
    return idle_result,starting_nodes_results


def get_nodes_by_multi_node_hc_expired(multi_node_hc_timeout):
    """Get all nodes whose active healthcheck is expired."""
    current_time = current_utc_time()
    time_th_multi_node = (current_time - multi_node_hc_timeout).replace(tzinfo=timezone.utc)
    active_hc_timeout=timedelta(minutes=2)
    time_th_active_hc = (current_time - active_hc_timeout).replace(tzinfo=timezone.utc)

    query = get_nodes_with_latest_healthchecks()

    # Map subquery columns
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    # Filters
    query = query.filter(label_map["role"] == "compute")
    logger.debug(f"Count after role filter: {query.count()}")

    query = query.filter(label_map["shape"].in_([
        "BM.GPU.H100.8", "BM.GPU.A100-v2.8", "BM.GPU4.8",
        "BM.GPU.B4.8", "BM.GPU.H200.8", "BM.GPU.GB200.4",
        "BM.GPU.B200.8", "BM.GPU.GB200-v2.4", "BM.GPU.GB200-v3.4", "BM.GPU.GB300.4", "BM.GPU.MI300X.8", "BM.GPU.MI355X.8", "BM.GPU.MI355X-v1.8", "BM.GPU.MI355X-v0.8"
    ]))
    logger.debug(f"Count after shape filter: {query.count()}")

    query = query.filter(label_map["slurm_state"] == "idle")
    logger.debug(f"Count after slurm state filter: {query.count()}")
    query = query.filter(label_map["passive_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after passive healthcheck Healthy filter: {query.count()}")
    query = query.filter(label_map["active_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after active healthcheck Healthy for 10 minutes filter: {query.count()}")

    query_healthy = query.filter(
        or_(
            label_map["multi_node_healthcheck_recommendation"] == "Healthy",
            label_map["multi_node_healthcheck_recommendation"] == "",
            label_map["multi_node_healthcheck_recommendation"].is_(None),
        )
    )
    logger.debug(f"Count after multi node healthcheck Healthy filter: {query_healthy.count()}")
    col = label_map.get("active_healthcheck_last_time")
    if col is not None:
        query_healthy = query_healthy.filter(
            or_(
                col.is_(None),
                cast(col, DateTime) < time_th_active_hc
            )
        )
    col = label_map.get("multi_node_healthcheck_last_time")
    if col is not None:
        query_healthy = query_healthy.filter(
            or_(
                col.is_(None),
                cast(col, DateTime) < time_th_multi_node
            )
        )
    logger.debug(f"Count after multi node healthcheck Healthy for 24 hours filter: {query_healthy.count()}")
    query_potentially_bad = query.filter(
        label_map["multi_node_healthcheck_status"] == "Potentially Bad"
    )
    logger.debug(f"Count after multi node healthcheck Potentially Bad filter: {query_potentially_bad.count()}")
    return query_healthy.all(), query_potentially_bad.all()


def get_nodes_for_initial_multi_node_check(multi_node_hc_timeout):
    """Get all nodes whose active healthcheck is expired."""
    current_time = current_utc_time()
    time_th_multi_node = (current_time - multi_node_hc_timeout).replace(tzinfo=timezone.utc)
    active_hc_timeout=timedelta(minutes=10)
    time_th_active_hc = (current_time - active_hc_timeout).replace(tzinfo=timezone.utc)

    query = get_nodes_with_latest_healthchecks()

    # Map subquery columns
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    # Filters
    query = query.filter(label_map["role"] == "compute")
    logger.debug(f"Count after role filter: {query.count()}")

    query = query.filter(label_map["shape"].in_([
        "BM.GPU.H100.8", "BM.GPU.A100-v2.8", "BM.GPU4.8",
        "BM.GPU.B4.8", "BM.GPU.H200.8", "BM.GPU.GB200.4",
        "BM.GPU.B200.8", "BM.GPU.GB200-v2.4", "BM.GPU.GB200-v3.4", "BM.GPU.GB300.4", "BM.GPU.MI300X.8", "BM.GPU.MI355X.8", "BM.GPU.MI355X-v1.8", "BM.GPU.MI355X-v0.8"
    ]))
    logger.debug(f"Count after shape filter: {query.count()}")

    query = query.filter(label_map["slurm_state"] == "resv")
    logger.debug(f"Count after slurm state filter: {query.count()}")
    query = query.filter(label_map["slurm_reservation"]=="InitialValidation")
    logger.debug(f"Count after slurm reservation check: {query.count()}")
    number_of_nodes=query.count()
    query = query.filter(label_map["passive_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after passive healthcheck Healthy filter: {query.count()}")
    query = query.filter(label_map["active_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after active healthcheck Healthy for 10 minutes filter: {query.count()}")

    query_healthy = query.filter(
        or_(
            label_map["multi_node_healthcheck_recommendation"] == "Healthy",
            label_map["multi_node_healthcheck_recommendation"] == "",
            label_map["multi_node_healthcheck_recommendation"].is_(None),
        )
    )
    col = label_map.get("multi_node_healthcheck_last_time")
    if col is not None:
        query_healthy = query_healthy.filter(
            or_(
                col.is_(None),
                cast(col, DateTime) < time_th_multi_node
            )
        )
    logger.debug(f"Count after multi node healthcheck Healthy filter: {query_healthy.count()}")
    query_potentially_bad = query.filter(
        label_map["multi_node_healthcheck_status"] == "Potentially Bad"
    )
    logger.debug(f"Count after multi node healthcheck Potentially Bad filter: {query_potentially_bad.count()}")
    return query_healthy.all(), query_potentially_bad.all()


def get_nodes_by_status(status):
    """Get all nodes with a specific status"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["status"] == status).all()
    return nodes


def get_nodes_by_shape(shape):
    """Get all nodes with a specific shape"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["shape"] == shape).all()
    return nodes

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
        
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    for column, value in filters_dict.items():
        if column in label_map:
            query = query.filter(label_map[column] == value)
    return query.all()


def get_nodes_by_hpc_island(hpc_island):
    """Get all nodes with a specific hpc_island"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["hpc_island"] == hpc_island).all()
    return nodes


def get_nodes_by_network_block(network_block):
    """Get all nodes with a specific network block"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["network_block_id"] == network_block).all()
    return nodes


def get_nodes_by_rail(rail_id):
    """Get all nodes with a specific rail ID"""
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    nodes = query.filter(label_map["rail_id"] == rail_id).all()
    return nodes



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


def db_update_node(node_row, **kwargs):
    """
    Update fields for a node in the Nodes table using a Row object or ocid.
    """
    session = query_db()
    try:
        ocid = node_row.ocid if hasattr(node_row, "ocid") else node_row
        node = session.query(Nodes).filter_by(ocid=ocid).one_or_none()
        if not node:
            logger.error(f"No node found with ocid={ocid}")
            return False

        for key, value in kwargs.items():
            if hasattr(node, key):
                setattr(node, key, value)
            elif "healthcheck" in key:
                logger.warning(f"Nodes cannot be updated with healthcheck attribute, update the healthchecks table instead.")
            else:
                logger.warning(f"Unknown attribute '{key}' ignored.")

        session.commit()
        return True

    except Exception as exc:
        logger.error(f"Error updating node {ocid}: {exc}")
        session.rollback()
        return False
    finally:
        session.close()

def db_update_healthcheck(healthcheck, hc_dict):
    """
    Update fields for a node in the database identified by its OCID.

    Args:
        ocid (str): The OCID of the node to update.
        hc_dict: Field names and values to update.

    Example:
        db_update_healthcheck(healthcheck, {"healthcheck_last_time": datetime.now()})
    """
    session = query_db()
    healthcheck = session.merge(healthcheck)
    try:
        for key, value in hc_dict.items():
            if hasattr(healthcheck, key):
                setattr(healthcheck, key, value)
            else:
                logger.warning(f"Unknown attribute '{key}' ignored.")
        session.commit()
        return True 
    except Exception as exc:
        logger.error(f"Error updating node {healthcheck.ocid}: {exc}")
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


def db_move_terminated_node(node_row):
    session = query_db()

    try:
        ocid = node_row.ocid if hasattr(node_row, "ocid") else node_row
        node = session.query(Nodes).filter_by(ocid=ocid).one_or_none()
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
        data['default_partition'] = False

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
            logger.warning(f"No configuration found: {configuration_name}")
            return False

        for key, value in kwargs.items():
            if hasattr(configuration, key):
                # Special handling for hostname_convention
                if key == 'hostname_convention' and not configuration.change_hostname:
                    setattr(configuration, key, value.lower() if value else value)
                else:
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
            logger.warning(f"No configuration found with name: {configuration_name}")
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
                change_hostname = instance.get("change_hostname", True)
                hostname_convention = instance.get("hostname_convention")
                
                # Apply lowercase if change_hostname is False
                if not change_hostname and hostname_convention:
                    hostname_convention = hostname_convention.lower()                
                # Map YAML keys to SQLAlchemy model fields
                config = Configurations(
                    role="compute",
                    name=instance.get("name"),
                    default_partition =  queue.get("default"),
                    partition=queue.get("name"),  # using queue name as partition
                    shape=instance.get("shape"),
                    change_hostname=change_hostname,
                    hostname_convention=hostname_convention,
                    permanent=instance.get("permanent", True),
                    rdma_enabled=instance.get("rdma_enabled", True),
                    stand_alone=instance.get("stand_alone", False),
                    max_number_nodes=instance.get("max_number_nodes",100),
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

        logins = yaml_data.get("login", [])
        for login in logins:
            config = Configurations(
                role="login",
                name=login.get("name"),
                default_partition =  queue.get("default"),
                partition=login.get("partition"),
                shape=login.get("shape"),
                change_hostname=login.get("change_hostname", True),
                hostname_convention=login.get("hostname_convention"),
                permanent=login.get("permanent", True),
                rdma_enabled=login.get("rdma_enabled", True),
                stand_alone=login.get("stand_alone", False),
                region=login.get("region"),
                availability_domain=login.get("availability_domain"),
                private_subnet_cidr=login.get("private_subnet"),
                private_subnet_id=login.get("private_subnet_id"),
                image_id=login.get("image_id"),
                target_compartment_id=login.get("target_compartment_id"),
                boot_volume_size=login.get("boot_volume_size", 50),
                max_number_nodes=login.get("max_number_nodes", 100),
                use_marketplace_image=login.get("use_marketplace_image", True),
                instance_pool_ocpus=login.get("instance_pool_ocpus"),
                instance_pool_custom_memory=login.get("instance_pool_custom_memory", False),
                instance_pool_memory=login.get("instance_pool_memory"),
                marketplace_listing=login.get("marketplace_listing"),
                hyperthreading=login.get("hyperthreading", True),
                preemptible=login.get("preemptible", False)
            )

            # Check if config already exists
            existing = session.query(Configurations).filter_by(name=config.name).first()
            if existing:
                logger.info(f"Configuration '{config.name}' already exists. Skipping.")
                continue

            session.add(config)
        session.commit()
        logger.info("All configurations successfully imported.")
        return True

    except Exception as exc:
        logger.error(f"Error importing configurations: {exc}")
        session.rollback()
        return False
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


def get_all_configs(role):
    """Show details about the configuration"""
    session = query_db()
    try:
        if role == "all":
            configs = session.query(Configurations).all()
        else:
            configs = session.query(Configurations).filter(Configurations.role == role).all()
        return configs
    finally:
        session.close()


def get_config_by_partition(partition, role):
    """Show details about the configuration"""
    session = query_db()
    try:
        if role == "all":
            configs = session.query(Configurations).filter(Configurations.partition == partition).all()
        else:
            configs = session.query(Configurations).filter(
                and_(Configurations.partition == partition,
                     Configurations.role == role
                     )
            ).all()
        return configs
    finally:
        session.close()


def get_config_by_shape(shape, role):
    """Show details about the configuration"""
    session = query_db()
    try:
        if role == "all":
            configs = session.query(Configurations).filter(Configurations.shape == shape).all()
        else:
            configs = session.query(Configurations).filter(
                and_(Configurations.shape == shape,
                     Configurations.role == role
                     )
            ).all()
        return configs
    finally:
        session.close()


def get_config_by_shape_and_partition(shape, partition, role):
    """Show details about the configuration"""
    session = query_db()
    try:
        if role == "all":
            configs = session.query(Configurations).filter(
                and_(Configurations.shape == shape,
                     Configurations.partition == partition
                     )
            ).all()
        else:
            configs = session.query(Configurations).filter(
                and_(Configurations.shape == shape,
                     Configurations.partition == partition,
                     Configurations.role == role
                     )
            ).all()
        return configs
    finally:
        session.close()

def db_delete_node(node):
    session = query_db()
    try:
        node = session.merge(node)  # Merge to ensure the object is in the session
        session.delete(node)
        session.commit()
    finally:
        session.close()
    
def db_get_healthchecks(node_ocid):
    session = query_db()
    try:
        healthchecks = session.query(HealthChecks).filter(HealthChecks.ocid == node_ocid).all()
        return healthchecks
    finally:
        session.close()
    
def db_get_latest_healthchecks(node_ocid):
    session = query_db()
    try:
        # Get the latest healthcheck for each type
        subq = (session.query(
                    HealthChecks.healthcheck_type,
                    func.max(HealthChecks.healthcheck_last_time).label('latest_time')
                )
                .filter(HealthChecks.ocid == node_ocid)
                .group_by(HealthChecks.healthcheck_type)
                .subquery())

        latest_healthchecks = (session.query(HealthChecks)
                              .join(
                                  subq,
                                  and_(
                                      HealthChecks.ocid == node_ocid,
                                      HealthChecks.healthcheck_type == subq.c.healthcheck_type,
                                      HealthChecks.healthcheck_last_time == subq.c.latest_time
                                  )
                              )
                              .all())
        
        return latest_healthchecks
    finally:
        session.close()

def db_create_healthcheck(node_ocid, hc_dict):
    """
    Create node with the fields if the node does not exists.

    Args:
        **kwargs: Field names and values to update.

    Example:
        db_create_node("ocid1.node.oc1..abc", status="running", controller_status="configured")
    """
    session = query_db()
    try:
        node = HealthChecks(ocid=node_ocid)
        session.add(node)

        for key, value in hc_dict.items():
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
        logger.info(f"Healthcheck for node OCID {node_ocid} upserted with {hc_dict}")
        return True
    except Exception as exc:
        session.rollback()
        logger.error(f"Error upserting healthcheck for node {node_ocid}: {exc}")
        return False
    finally:
        session.close()

def get_nodes_validated():

    current_time = current_utc_time()
    time_th_active_hc = (current_time - timedelta(hours=1)).replace(tzinfo=timezone.utc)
    query = get_nodes_with_latest_healthchecks()
    label_map = {c["name"]: c["expr"] for c in query.column_descriptions if "expr" in c}
    query = query.filter(label_map["role"] == "compute")
    logger.debug(f"Count after role compute filter: {query.count()}")
    query = query.filter(label_map["slurm_state"] == "resv")
    nodes_in_validation_count = query.count()
    logger.debug(f"Count after slurm_state resv filter: {nodes_in_validation_count}")
    query = query.filter(label_map["slurm_reservation"] == "InitialValidation")
    logger.debug(f"Count after slurm_reservation InitialValidation filter: {query.count()}")
    query = query.filter(label_map["passive_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after passive_healthcheck_recommendation Healthy filter: {query.count()}")
    query = query.filter(label_map["active_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after active_healthcheck_recommendation Healthy filter: {query.count()}")


    query_validated = query.filter(label_map["multi_node_healthcheck_recommendation"] == "Healthy")
    logger.debug(f"Count after multi_node_healthcheck_recommendation Healthy filter: {query_validated.count()}")
    col = label_map.get("multi_node_healthcheck_last_time")
    if col is not None:
        query_validated = query_validated.filter( cast(col, DateTime) >= time_th_active_hc )
    logger.debug(f"multi_node_healthcheck_last_time: {query_validated.count()}")

    query_not_validated = query.except_(query_validated)
    if query_not_validated == 1 :
        query_not_validated = query_not_validated.filter(col.is_(None))
        col = label_map.get("active_healthcheck_recommendation")
        if col is not None:
            query_not_validated = query_not_validated.filter( cast(col, DateTime) >= (current_time - timedelta(minutes=10)).replace(tzinfo=timezone.utc) )
            logger.debug(f"Count after active_healthcheck_last_time filter: {query_not_validated.count()}")

    return query_not_validated.union(query_validated)