#!/usr/bin/env python3
"""
OCI Monitoring to Telegraf InfluxDB Line Protocol Converter

This script continuously fetches metrics from the Oracle Cloud Infrastructure (OCI) Monitoring API
and outputs them in the Telegraf InfluxDB line protocol format for consumption by Telegraf.

Environment Variables:
    OCI_CONFIG_PATH: Path to OCI configuration file (optional). If not set, instance principal
                     authentication will be attempted.
    OCI_PROFILE: OCI profile name to use from config file (default: "DEFAULT")
    OCI_REGION: OCI region identifier. If not set, will be auto-detected from instance metadata.
    OCI_COMPARTMENT_ID: OCID of the compartment to query metrics from. If not set, will be
                        auto-detected from instance metadata.

Usage:
    Run as a standalone script (typically invoked by Telegraf exec input plugin):
        $ python3 oci_metrics_telegraf_monitoring_input.py

    The script outputs metrics to stdout in InfluxDB line protocol format:
        <measurement>,<tag_key>=<tag_value> <field_key>=<field_value> <timestamp_ns>

    Example output:
        oci_objectstorage:AllRequests,namespace=oci_objectstorage,bucketId=ocid1.bucket... count=1234 1704067200000000000

Architecture:
    1. Initializes OCI Monitoring API client with appropriate authentication
    2. Creates a continuous metrics fetcher with rate limiting
    3. Registers metric queries to be polled
    4. Runs a worker thread that fetches missing minute-interval data
    5. Converts OCI metric responses to InfluxDB line protocol
    6. Outputs metrics to stdout for Telegraf consumption

Rate Limiting:
    Implements a token bucket rate limiter to enforce RPS (requests per second)
    and RPM (requests per minute) limits, preventing API throttling.

Features:
    - Continuous polling with gap-filling (no minute intervals lost)
    - Configurable rate limiting
    - Multiple concurrent metric queries
    - Graceful shutdown on SIGHUP or SIGINT
    - Instance principal or config file authentication
"""

import json
import logging
import os
import queue
import signal
import sys
import threading
import traceback

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
from influx_line_protocol import Metric
from oci.monitoring import MonitoringClient
from oci.monitoring.models import SummarizeMetricsDataDetails
from oci.retry import DEFAULT_RETRY_STRATEGY
from urllib.request import Request, urlopen

# OCI Configuration from environment
# See module docstring for details on each variable
OCI_CONFIG_PATH = os.environ.get("OCI_CONFIG_PATH", "")
OCI_PROFILE = os.environ.get("OCI_PROFILE", "DEFAULT")
OCI_REGION = os.environ.get("OCI_REGION", None)
OCI_COMPARTMENT_ID = os.environ.get("OCI_COMPARTMENT_ID", None)

# Default OCI Object Storage metrics to collect
# Format: "namespace:metric_definition[resolution].aggregation()"
# These metrics are polled continuously in one-minute intervals
metrics_to_collect = [
    "oci_objectstorage:AllRequests[1m].sum()",
    "oci_objectstorage:ClientErrors[1m].sum()",
    "oci_objectstorage:DeleteRequests[1m].sum()",
    "oci_objectstorage:FirstByteLatency[1m].mean()",
    "oci_objectstorage:GetRequests[1m].sum()",
    "oci_objectstorage:ListRequests[1m].sum()",
    "oci_objectstorage:ObjectCount[1m].mean()",
    "oci_objectstorage:PutRequests[1m].sum()",
    "oci_objectstorage:StoredBytes[1m].mean()",
    "oci_objectstorage:TotalRequestLatency[1m].mean()",
    "oci_objectstorage:UncommittedParts[1m].sum()"
]

logger = logging.getLogger(__name__)

class TelegrafFormatter(logging.Formatter):
    """
    Custom log formatter that prefixes log messages with level indicators.

    Prefixes log messages with single-letter level indicators for easier parsing:
    - 'I:' for INFO
    - 'E:' for ERROR
    - 'W:' for WARNING
    - 'D:' for DEBUG
    - No prefix for other levels

    This format is compatible with Telegraf's log parsing expectations.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def formatMessage(self, record: logging.LogRecord) -> str:
        """
        Format the log record with a level prefix.

        Args:
            record: The logging LogRecord to format

        Returns:
            Formatted log message string with level prefix
        """
        if record.levelno == logging.INFO:
            return f"I: {super().formatMessage(record)}"
        elif record.levelno == logging.ERROR:
            return f"E: {super().formatMessage(record)}"
        elif record.levelno == logging.WARNING:
            return f"W: {super().formatMessage(record)}"
        elif record.levelno == logging.DEBUG:
            return f"D: {super().formatMessage(record)}"
        else:
            return super().formatMessage(record)

def parse_timestamp(timestamp_str: str) -> int:
    """
    Parse ISO 8601 timestamp string to Unix nanoseconds.

    Converts an ISO 8601 formatted timestamp (e.g., '2024-01-01T00:00:00.000Z')
    to Unix nanoseconds since epoch for use in InfluxDB line protocol.

    Args:
        timestamp_str: ISO 8601 timestamp string (may include '+00:00' timezone suffix)

    Returns:
        int: Unix timestamp in nanoseconds

    Example:
        >>> parse_timestamp('2024-01-01T00:00:00.000Z')
        1704067200000000000
    """
    dt = datetime.fromisoformat(timestamp_str.replace('+00:00', ''))
    dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1e9)


def to_influxdb_line_protocol(metric_data: Dict[str, Any]) -> Optional[List[Metric]]:
    """
    Convert OCI Monitoring API metric data to InfluxDB line protocol format.

    Transforms OCI metric responses into a list of Metric objects compatible with
    Telegraf's InfluxDB line protocol output. Extracts measurement name from
    namespace:metric_name, creates tags from dimensions (excluding resourceDisplayName),
    and processes all aggregated datapoints.

    Args:
        metric_data: OCI metric data containing:
            - namespace (str): OCI service namespace
            - name (str): Metric name
            - dimensions (dict, optional): Key-value pairs for tagging
            - aggregated_datapoints (list): List of datapoints with timestamp and value

    Returns:
        List of Metric objects in InfluxDB line protocol format,
        or None if conversion fails or required fields are missing

    Side Effects:
        Logs warnings for invalid metric format
        Logs errors for conversion failures
        Logs debug messages for successful conversions

    Example:
        >>> metric_data = {
        ...     'namespace': 'oci_objectstorage',
        ...     'name': 'AllRequests',
        ...     'dimensions': {'bucketId': 'ocid1.bucket...'},
        ...     'aggregated_datapoints': [
        ...         {'timestamp': '2024-01-01T00:00:00.000Z', 'value': 1234}
        ...     ]
        ... }
        >>> result = to_influxdb_line_protocol(metric_data)
    """
    try:
        # Validate required fields
        if 'aggregated_datapoints' not in metric_data or 'namespace' not in metric_data or 'name' not in metric_data:
            logger.warning(f"Invalid metric format: missing required fields in {metric_data}")
            return None
        logger.debug(f"Converting valid metric: {metric_data}")
        results = []

        measurement = f"{metric_data['namespace']}:{metric_data['name']}"

        # Build tags from dimensions (excluding resourceDisplayName which is too verbose/variable)
        tags = {"namespace": metric_data['namespace']}

        if "dimensions" in metric_data:
            for key, value in metric_data["dimensions"].items():
                # Skip resourceDisplayName as it creates high-cardinality tags
                if key == "resourceDisplayName":
                    continue
                if value is not None:
                    tags[key] = str(value)

        for entry in metric_data['aggregated_datapoints']:
            if 'timestamp' not in entry or 'value' not in entry:
                continue

            influx_metric = Metric(measurement)
            
            influx_metric.with_timestamp(parse_timestamp(entry["timestamp"]))
            
            for key, value in tags.items():
                if value:
                    influx_metric.add_tag(key, str(value))

            influx_metric.add_value("count", entry["value"])
            results.append(influx_metric)

        logger.debug(f"Returning the influxDB metrics: {', '.join((str(r) for r in results))}")
        return results

    except Exception as e:
        logger.error(f"Failed to convert to InfluxDB line protocol: {traceback.format_exc()}")
        return None

class RateLimiter:
    """
    Token bucket rate limiter to control API request rates.

    Implements a dual token bucket algorithm to enforce both RPS (requests per second)
    and RPM (requests per minute) limits. Tokens are replenished over time, and acquire()
    blocks until tokens are available for both limits or timeout occurs.

    This prevents API throttling by ensuring the client stays within OCI's API rate limits.

    Attributes:
        max_rps: Maximum requests per second limit
        max_rpm: Maximum requests per minute limit
        tokens_rps: Current available RPS tokens
        tokens_rpm: Current available RPM tokens
        last_update_rps: Last time RPS tokens were updated
        last_update_rpm: Last time RPM tokens were updated
        lock: Thread lock for atomic token operations
    """

    def __init__(self, max_rps: int = 10, max_rpm: int = 100):
        """
        Initialize rate limiter with specified limits.

        Args:
            max_rps: Maximum requests per second (default: 10)
            max_rpm: Maximum requests per minute (default: 100, not 500)
                     Note: docstring previously stated 500, but code uses 100
        """
        self.max_rps = max_rps
        self.max_rpm = max_rpm
        self.tokens_rps = max_rps
        self.tokens_rpm = max_rpm
        self.last_update_rps = datetime.now(timezone.utc)
        self.last_update_rpm = datetime.now(timezone.utc)
        self.lock = threading.Lock()

    def acquire(self, timeout: int = 60) -> bool:
        """
        Acquire a token from the bucket. Blocks until a token is available or timeout.

        Args:
            timeout: Maximum time to wait in seconds (default: 60)

        Returns:
            True if token acquired successfully, False if timeout occurred
        """
        start_time = datetime.now(timezone.utc)

        while True:
            with self.lock:
                now = datetime.now(timezone.utc)

                # Refill RPS tokens based on elapsed time
                # Tokens accumulate at max_rps per second (e.g., 10 RPS = 10 tokens/second)
                elapsed_rps = (now - self.last_update_rps).total_seconds()
                self.tokens_rps = min(self.max_rps, self.tokens_rps + elapsed_rps * self.max_rps)
                self.last_update_rps = now

                # Refill RPM tokens based on elapsed time
                # Tokens accumulate at max_rpm per minute (e.g., 100 RPM = 1.67 tokens/second)
                elapsed_rpm = (now - self.last_update_rpm).total_seconds() / 60
                self.tokens_rpm = min(self.max_rpm, self.tokens_rpm + elapsed_rpm * self.max_rpm)
                self.last_update_rpm = now

                # Check if we have tokens for both limits
                if self.tokens_rps >= 1 and self.tokens_rpm >= 1:
                    self.tokens_rps -= 1
                    self.tokens_rpm -= 1
                    return True

            # Check timeout
            if (datetime.now(timezone.utc) - start_time).total_seconds() >= timeout:
                return False

            # Wait a bit before trying again
            threading.Event().wait(0.1)


class OCIContinuousMetricsFetcher:
    """
    Continuous metrics fetcher with gap-filling and rate limiting.

    Manages continuous polling of OCI Monitoring API metrics for multiple queries.
    Implements gap-filling logic to ensure no minute intervals are missed, even if
    the script temporarily stops or the API experiences issues. Uses a background
    worker thread that periodically fetches missing data intervals.

    The fetcher tracks the last successful fetch time for each query and fills in
    all missing minute-intervals on each polling cycle, ensuring complete data coverage.

    Attributes:
        monitoring_client: Authenticated OCI MonitoringClient instance
        compartment_id: OCI compartment OCID for queries
        metrics_queue: Queue where fetched metrics are deposited
        stop_event: Threading event to signal graceful shutdown
        thread: Background worker thread
        rate_limiter: RateLimiter instance for API throttling
        queries: List of query configurations to fetch
        last_fetch_times: Dict tracking last successful fetch per query

    Workflow:
        1. Configure queries using add_query()
        2. Start background worker with start()
        3. Worker polls for missing intervals every poll_interval_seconds
        4. Fetches are rate-limited to prevent API throttling
        5. Retrieved metrics are placed in metrics_queue
        6. Stop gracefully with stop()
    """

    def __init__(
        self,
        monitoring_client: MonitoringClient,
        compartment_id: Optional[str] = None,
        max_rps: int = 10,
        max_rpm: int = 500
    ):
        """
        Initialize the continuous metrics fetcher.

        Args:
            monitoring_client: Authenticated OCI MonitoringClient instance
            compartment_id: OCI compartment OCID. If None, uses OCI_COMPARTMENT_ID env var
            max_rps: Maximum requests per second (default: 10)
            max_rpm: Maximum requests per minute (default: 500)
        """
        self.monitoring_client = monitoring_client
        self.compartment_id = compartment_id or OCI_COMPARTMENT_ID
        self.metrics_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self.rate_limiter = RateLimiter(max_rps=max_rps, max_rpm=max_rpm)

        # Query configurations: list of dicts with 'namespace', 'query', 'compartment_id' (optional)
        self.queries = []

        # Track last fetch time for each query (key: namespace:query)
        self.last_fetch_times = {}

    def add_query(
        self,
        namespace: str,
        query: str,
        compartment_id: Optional[str] = None
    ) -> None:
        """
        Add a query configuration to be fetched continuously.

        Args:
            namespace: The OCI service namespace (e.g., 'oci_objectstorage')
            query: The metric query in OCI query syntax
            compartment_id: Override compartment ID for this query (optional)
        """
        query_config = {
            'namespace': namespace,
            'query': query,
            'compartment_id': compartment_id or self.compartment_id
        }
        self.queries.append(query_config)

        # Initialize last fetch time to 2 minutes ago for new queries
        key = f"{namespace}:{query}"
        if key not in self.last_fetch_times:
            self.last_fetch_times[key] = datetime.now(timezone.utc) - timedelta(minutes=2)

        logger.info(f"Added query: {namespace}:{query}")

    def _truncate_to_minute(self, dt: datetime) -> datetime:
        """Truncate datetime to the start of the minute."""
        return dt.replace(second=0, microsecond=0)

    def fetch_interval(
        self,
        namespace: str,
        query: str,
        compartment_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[Any]:
        """
        Fetch metrics for a specific time interval with rate limiting.

        Args:
            namespace: The OCI service namespace
            query: The metric query
            compartment_id: The compartment ID
            start_time: Start of interval
            end_time: End of interval

        Returns:
            The metrics data response, or None if an error occurs
        """
        # Wait for rate limiter
        if not self.rate_limiter.acquire(timeout=60):
            logger.error(f"Rate limiter timeout for {namespace}:{query}")
            return None

        try:
            response = self.monitoring_client.summarize_metrics_data(
                compartment_id=compartment_id,
                summarize_metrics_data_details=SummarizeMetricsDataDetails(
                    namespace=namespace,
                    query=query,
                    start_time=start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                    end_time=end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
                ),
                compartment_id_in_subtree=False
            )

            if response.status != 200:
                logger.error(f"Error fetching metrics for {namespace}:{query} for interval {start_time.isoformat()} {end_time.isoformat()}. Error: response status {response.status}")
                return None

            # Put metrics data into queue
            self.metrics_queue.put(str(response.data))

            logger.debug(f"Fetched metrics for {namespace}:{query} for interval {start_time.isoformat()} {end_time.isoformat()}")
            return response.data

        except Exception as e:
            logger.error(f"Error fetching metrics for {namespace}:{query} for interval {start_time.isoformat()} {end_time.isoformat()}. Error: {traceback.format_exc()}")
            return None

    def fetch_missing_intervals_for_query(self, query_config: Dict[str, str]) -> int:
        """
        Fetch all missing intervals for a specific query.

        Args:
            query_config: Dict with 'namespace', 'query', 'compartment_id'

        Returns:
            Number of intervals successfully fetched
        """
        namespace = query_config['namespace']
        query = query_config['query']
        compartment_id = query_config['compartment_id']

        now = self._truncate_to_minute(datetime.now(timezone.utc) - timedelta(minutes=1))
        key = f"{namespace}:{query}"
        last_fetch = self._truncate_to_minute(self.last_fetch_times.get(key, now - timedelta(minutes=1)))

        # Calculate how many minute intervals we need to fetch
        intervals_to_fetch = int((now - last_fetch).total_seconds() / 60)

        if intervals_to_fetch <= 0:
            return 0

        logger.debug(f"Fetching {intervals_to_fetch} intervals for {namespace}:{query}")

        intervals_fetched = 0

        # Fetch each minute interval
        for i in range(intervals_to_fetch):
            if self.stop_event.is_set():
                break

            interval_start = last_fetch + timedelta(minutes=i)
            interval_end = interval_start + timedelta(minutes=1)

            data = self.fetch_interval(namespace, query, compartment_id, interval_start, interval_end)

            if data is not None:
                intervals_fetched += 1
                # Update last fetch time only on success
                self.last_fetch_times[key] = interval_end

        return intervals_fetched

    def worker(self, poll_interval_seconds: int = 30) -> None:
        """
        Worker that continuously polls for missing intervals across all queries.

        Args:
            poll_interval_seconds: How often to check for new intervals (default: 30s)
        """
        logger.info(f"Starting metrics fetcher for {len(self.queries)} queries")

        while not self.stop_event.is_set():
            try:
                # Fetch missing intervals for each query
                for query_config in self.queries:
                    if self.stop_event.is_set():
                        break

                    self.fetch_missing_intervals_for_query(query_config)

            except Exception as e:
                logger.error(f"Error in metrics fetcher worker: {traceback.format_exc()}")

            # Wait before next poll (or until stop event)
            self.stop_event.wait(poll_interval_seconds)

        logger.info("Metrics fetcher stopped")

    def start(self, poll_interval_seconds: int = 30) -> queue.Queue:
        """
        Start the continuous metrics fetcher in a background thread.

        Args:
            poll_interval_seconds: How often to check for new intervals (default: 30s)

        Returns:
            The metrics queue where results will be posted
        """
        if not self.queries:
            logger.warning("No queries configured. Use add_query() to add queries first.")

        if self.thread is not None and self.thread.is_alive():
            logger.warning("Metrics fetcher is already running")
            return self.metrics_queue

        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self.worker,
            args=(poll_interval_seconds,),
            daemon=True
        )
        self.thread.start()

        return self.metrics_queue

    def stop(self) -> None:
        """Stop the metrics fetcher gracefully."""
        if self.thread and self.thread.is_alive():
            logger.info("Stopping metrics fetcher...")
            self.stop_event.set()
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logger.warning("Metrics fetcher did not stop gracefully")
        else:
            logger.info("Metrics fetcher is not running")

    def get_metrics(self, block: bool = False, timeout: int = 5) -> Optional[str]:
        """
        Get metrics from the queue.

        Args:
            block: Whether to block if queue is empty
            timeout: Maximum time to wait for a metric (seconds)

        Returns:
            Metric data JSON string or None if timeout occurs
        """
        try:
            return self.metrics_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None


def get_instance_metadata() -> Optional[Dict[str, Any]]:
    """
    Fetch OCI instance metadata from the instance metadata service.

    Retrieves instance metadata such as region name and compartment ID from
    the OCI instance metadata service (available on OCI compute instances).

    Returns:
        Instance metadata dictionary containing keys like:
        - 'canonicalRegionName': Region identifier
        - 'compartmentId': Compartment OCID
        Returns None on error.

    Note:
        Only works when running on an OCI compute instance with access to
        169.254.169.254 metadata service. Uses 'Bearer Oracle' authentication.
    """
    try:
        req = Request('http://169.254.169.254/opc/v2/instance/')
        req.add_header('Authorization', 'Bearer Oracle')
        content = urlopen(req, timeout=10).read()

        instance_metadata = json.loads(content.decode('utf-8'))
        return instance_metadata
    except Exception as e:
        logger.error(f"Failed to get region: {traceback.format_exc()}")
        return None


if __name__ == "__main__":
    # Setup logging with Telegraf-compatible formatter
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    formatter = TelegrafFormatter(fmt='%(asctime)s - %(name)s - %(threadName)s - %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Auto-detect region and compartment_id from instance metadata if not set
    instance_metadata = get_instance_metadata()
    if not OCI_REGION:
        if instance_metadata:
            OCI_REGION = instance_metadata['canonicalRegionName']
        if not OCI_REGION:
            logger.error("Could not determine OCI region")
            sys.exit(1)

    logger.info("Using OCI region: {}".format(OCI_REGION))

    if not OCI_COMPARTMENT_ID:
        if instance_metadata:
            OCI_COMPARTMENT_ID = instance_metadata['compartmentId']
        if not OCI_COMPARTMENT_ID:
            logger.error("Could not determine OCI compartment ID")
            sys.exit(1)

    logger.info("Using OCI compartment ID: {}".format(OCI_COMPARTMENT_ID))

    # Authentication: Try config file first, fall back to instance principal
    auth = False

    try:
        # Try to load credentials from OCI config file
        from oci.config import from_file
        if OCI_CONFIG_PATH:
            logger.info(f"OCI CONFIG PATH: {OCI_CONFIG_PATH}")
            config = from_file(file_location=OCI_CONFIG_PATH, profile_name="DEFAULT")
        else:
            config = from_file(profile_name="DEFAULT")

        if OCI_REGION:
            config["region"] = OCI_REGION

        from oci import Signer
        signer = Signer.from_config(config)
        auth = True
    except Exception as e:
        logger.error(f'Failed to load profile and signer from the OCI config file: {e}')

    if not auth:
        # Fall back to instance principal authentication
        logger.info('Attempting to use instance_principal...')
        try:
            from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
            config = {}
            if OCI_REGION:
                config["region"] = OCI_REGION
            signer = InstancePrincipalsSecurityTokenSigner()
        except Exception as e:
            logger.error(f"Failed to load instance principal signer. No supported signer found: {traceback.format_exc()}")
            sys.exit(1)

    logger.info(f'Getting object storage metrics from compartment: {OCI_COMPARTMENT_ID}')

    # Initialize Monitoring client with retry strategy for resilience
    monitoring_client = MonitoringClient(config=config, signer=signer, retry_strategy=DEFAULT_RETRY_STRATEGY)

    # Initialize continuous metrics fetcher with conservative rate limits
    # to leave room for other API calls and avoid throttling
    fetcher = OCIContinuousMetricsFetcher(
        monitoring_client,
        max_rps=1,
        max_rpm=30
    )

    # Register all configured metrics queries
    for entry in metrics_to_collect:
        ns, query = entry.split(":")
        fetcher.add_query(ns, query)

    # Setup graceful shutdown handler for SIGHUP signal
    def graceful_shutdown(signum, frame):
        """Handles SIGHUP signal for graceful shutdown"""
        fetcher.stop()
        logger.info("Received SIGHUP, exiting...")
        sys.exit(0)

    signal.signal(signal.SIGHUP, graceful_shutdown)

    try:
        # Start the continuous fetcher with 10-second polling interval
        metrics_queue = fetcher.start(poll_interval_seconds=10)

        # Main loop: Process metrics as they arrive in the queue
        while True:
            oci_metrics_summary = fetcher.get_metrics(block=True, timeout=1)
            if oci_metrics_summary:
                # Parse JSON response (may contain multiple metric summaries)
                oci_metrics_summary_list = json.loads(oci_metrics_summary)
                for oci_metrics_summary in oci_metrics_summary_list:
                    # Convert each OCI metric to InfluxDB line protocol
                    influx_metrics = to_influxdb_line_protocol(oci_metrics_summary)
                    if influx_metrics:
                        # Output each datapoint to stdout for Telegraf
                        for influx_metric in influx_metrics:
                            print(str(influx_metric), file=sys.stdout, flush=True)

    except KeyboardInterrupt:
        fetcher.stop()
        logger.info("Interrupted by user, exiting...")

    except Exception:
        logger.info(f"An unexpected error occured: {traceback.format_exc()}")
