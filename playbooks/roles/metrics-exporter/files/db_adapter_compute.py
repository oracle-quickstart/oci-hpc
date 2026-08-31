#!/usr/bin/env python3
"""
Database Adapter for NVML Metrics Exporter

MySQL-only adapter for storing job utilization data from compute nodes.
All compute nodes write to a central MySQL database for cluster-wide aggregation.

Environment Variables:
    SLURM_DB_HOST       - MySQL host (required)
    SLURM_DB_PORT       - MySQL port (default: 3306)
    SLURM_DB_USER       - MySQL user (default: slurm)
    SLURM_DB_PASSWORD   - MySQL password (required)
    SLURM_DB_NAME       - MySQL database name (default: slurm_jobs)

Usage:
    from db_adapter_compute import get_adapter

    db = get_adapter().connect()
    db.execute("INSERT INTO job_utilization ...", params)
    db.close()
"""

import os
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MySQLAdapter:
    """MySQL adapter for NVML metrics storage with auto-reconnect."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.config = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
            'autocommit': True,
            'charset': 'utf8mb4',
            'connection_timeout': 10,
        }
        self.conn = None
        self._mysql_connector = None

    def connect(self) -> 'MySQLAdapter':
        """Connect to a MySQL database provisioned by Ansible."""
        try:
            import mysql.connector
            self._mysql_connector = mysql.connector

            self.conn = mysql.connector.connect(**self.config)
            logger.info(f"Connected to MySQL: {self.config['host']}:{self.config['port']}/{self.config['database']}")
        except ImportError:
            raise ImportError("mysql-connector-python required. Install: pip install mysql-connector-python")
        self.validate_schema()
        return self

    def _ensure_connected(self) -> None:
        """Ensure database connection is alive, reconnect if needed."""
        try:
            if self.conn is None or not self.conn.is_connected():
                logger.info("MySQL connection lost, reconnecting...")
                self.conn = self._mysql_connector.connect(**self.config)
                logger.info("MySQL reconnected successfully")
        except Exception as e:
            logger.error(f"Failed to reconnect to MySQL: {e}")
            raise

    def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        """Execute a single query with auto-reconnect."""
        self._ensure_connected()
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor

    def executemany(self, query: str, params_list: List[Tuple]) -> Any:
        """Execute a query with multiple parameter sets."""
        self._ensure_connected()
        cursor = self.conn.cursor(dictionary=True)
        cursor.executemany(query, params_list)
        return cursor

    def fetchall(self, query: str, params: Optional[Tuple] = None) -> List[Dict]:
        """Execute query and fetch all results."""
        self._ensure_connected()
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchall()

    def fetchone(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict]:
        """Execute query and fetch one result."""
        self._ensure_connected()
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchone()

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
            logger.debug("MySQL connection closed")

    def validate_schema(self) -> None:
        """Fail fast if Ansible did not provision job_utilization."""
        row = self.fetchone(
            """
            SELECT table_name AS table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = 'job_utilization'
            """,
            (self.config['database'],),
        )
        if not row:
            raise RuntimeError(
                "Slurm monitoring database schema is missing table job_utilization. "
                "Run the Slurm monitoring database Ansible tasks before starting exporters."
            )


def get_adapter() -> MySQLAdapter:
    """
    Get MySQL database adapter configured from environment variables.

    Environment variables:
        SLURM_DB_HOST       - MySQL host (required)
        SLURM_DB_PORT       - MySQL port (default: 3306)
        SLURM_DB_USER       - MySQL user (default: slurm)
        SLURM_DB_PASSWORD   - MySQL password (required)
        SLURM_DB_NAME       - MySQL database name (default: slurm_jobs)

    Returns:
        MySQLAdapter instance (not connected - call .connect())
    """
    host = os.environ.get('SLURM_DB_HOST')
    password = os.environ.get('SLURM_DB_PASSWORD')

    if not host:
        raise ValueError("SLURM_DB_HOST environment variable is required")
    if not password:
        raise ValueError("SLURM_DB_PASSWORD environment variable is required")

    return MySQLAdapter(
        host=host,
        port=int(os.environ.get('SLURM_DB_PORT', 3306)),
        user=os.environ.get('SLURM_DB_USER', 'slurm'),
        password=password,
        database=os.environ.get('SLURM_DB_NAME', 'slurm_jobs')
    )
