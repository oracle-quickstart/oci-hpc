#!/usr/bin/env python3
"""
MySQL adapter for Slurm monitoring controller exporters.

Ansible owns database, user, grant, table, and index creation. This adapter only
connects to the provisioned MySQL schema and provides query helpers.

Environment Variables:
    SLURM_DB_HOST       - MySQL host (required)
    SLURM_DB_PORT       - MySQL port (default: 3306)
    SLURM_DB_USER       - MySQL user (default: slurm_exporter)
    SLURM_DB_PASSWORD   - MySQL password (required)
    SLURM_DB_NAME       - MySQL database name (default: slurm_jobs)
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MySQLAdapter:
    """MySQL adapter with reconnect handling."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.config = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "autocommit": True,
            "charset": "utf8mb4",
            "connection_timeout": 10,
        }
        self.conn = None
        self._mysql_connector = None

    def connect(self) -> "MySQLAdapter":
        """Connect to an Ansible-provisioned MySQL database."""
        try:
            import mysql.connector
        except ImportError as exc:
            raise ImportError(
                "mysql-connector-python required. Install: pip install mysql-connector-python"
            ) from exc

        self._mysql_connector = mysql.connector
        self.conn = mysql.connector.connect(**self.config)
        logger.info(
            "Connected to MySQL database: %s:%s/%s",
            self.config["host"],
            self.config["port"],
            self.config["database"],
        )
        return self

    def _ensure_connected(self) -> None:
        """Reconnect if the MySQL connection has been lost."""
        if self.conn is None or not self.conn.is_connected():
            logger.info("MySQL connection lost, reconnecting")
            self.conn = self._mysql_connector.connect(**self.config)
            logger.info("MySQL reconnected successfully")

    def execute(self, query: str, params: Optional[Tuple] = None) -> Any:
        """Execute a query and return the cursor."""
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
        """Execute a query and return all rows as dictionaries."""
        self._ensure_connected()
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchall()

    def fetchone(self, query: str, params: Optional[Tuple] = None) -> Optional[Dict]:
        """Execute a query and return one row as a dictionary."""
        self._ensure_connected()
        cursor = self.conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        return cursor.fetchone()

    def validate_schema(self) -> None:
        """Fail fast if Ansible did not provision the expected tables."""
        rows = self.fetchall(
            """
            SELECT table_name AS table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name IN ('jobs', 'job_utilization')
            """,
            (self.config["database"],),
        )
        found_tables = {row["table_name"] for row in rows}
        missing_tables = {"jobs", "job_utilization"} - found_tables
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise RuntimeError(
                f"Slurm monitoring database schema is missing table(s): {missing}. "
                "Run the Slurm monitoring database Ansible tasks before starting exporters."
            )

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None
            logger.debug("MySQL connection closed")


def get_adapter(config: Optional[Dict] = None) -> MySQLAdapter:
    """Return a MySQL adapter configured from explicit values or environment."""
    if config is None:
        config = {}

    host = config.get("host") or os.environ.get("SLURM_DB_HOST")
    password = config.get("password") or os.environ.get("SLURM_DB_PASSWORD")

    if not host:
        raise ValueError("SLURM_DB_HOST environment variable is required")
    if not password:
        raise ValueError("SLURM_DB_PASSWORD environment variable is required")

    return MySQLAdapter(
        host=host,
        port=int(config.get("port") or os.environ.get("SLURM_DB_PORT", 3306)),
        user=config.get("user") or os.environ.get("SLURM_DB_USER", "slurm_exporter"),
        password=password,
        database=config.get("database") or os.environ.get("SLURM_DB_NAME", "slurm_jobs"),
    )
