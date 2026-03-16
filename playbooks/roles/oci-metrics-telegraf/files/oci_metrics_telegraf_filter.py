#!/usr/bin/env python3
"""
OCI Metrics Telegraf Filter Plugin

This script acts as a filter plugin for Telegraf that enriches Oracle Cloud Infrastructure (OCI)
metrics with additional resource metadata tags fetched from the OCI API.

Key Features:
- Reads metrics in InfluxDB line protocol format from stdin
- Fetches resource tags and metadata from OCI API to enrich metrics
- Resolves Slurm hostnames from /etc/hosts for compute instances
- Supports caching to minimize API calls (LFU cache)
- Threaded execution for parallel resource tag enrichment
- Configurable metric filtering based on freeform tags
- Graceful shutdown via SIGHUP signal

Environment Variables:
    ENRICH_METRICS: Enable tag enrichment (default: false)
    TAG_DISCOVER_WORKERS: Number of worker threads for tag discovery (default: 10)
    OCI_CONFIG_PATH: Path to OCI config file (optional)
    DISCARD_METRICS_FOR_UNTAGGED_RESOURCES: Discard metrics without required tags (default: true)

Usage:
    Metrics are piped to this script via stdin, and enriched metrics are output to stdout.
    The script operates in two modes based on ENRICH_METRICS:
    - True: Enriches metrics with OCI resource tags
    - False: Passes through metrics without enrichment (useful for debugging)
"""

import json
import logging
import os
import re
import signal
import sys
import time
import traceback
from typing import Dict, Any, Optional, Tuple

from concurrent.futures import ThreadPoolExecutor, Future
from threading import Thread, Lock

from cachetools.func import lfu_cache
from line_protocol_parser import parse_line
from influx_line_protocol import Metric
from urllib.request import Request, urlopen


os.environ["OCI_PYTHON_SDK_NO_SERVICE_IMPORTS"] = "1"

from oci.retry import RetryStrategyBuilder, BACKOFF_FULL_JITTER_EQUAL_ON_THROTTLE_VALUE

from oci_metrics_telegraf_utils import OCIMetaClient, flatten_dict

logger = logging.getLogger(__name__)

oci_client = None

class TelegrafFormatter(logging.Formatter):
    """Custom log formatter that adds level prefixes to log messages.

    Prefixes log messages with single-letter level indicators:
    - I: INFO
    - E: ERROR
    - W: WARNING
    - D: DEBUG

    This format is compatible with Telegraf's log parsing expectations.
    """

    def __init__(self, **kwargs):
        """Initialize the formatter with parent class arguments."""
        super().__init__(**kwargs)

    def formatMessage(self, record: logging.LogRecord) -> str:
        """Format a log message with level prefix.

        Args:
            record: The logging record to format.

        Returns:
            str: The formatted log message with level prefix.
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

# Configuration from environment variables
ENRICH_METRICS = os.environ.get("ENRICH_METRICS", "false").lower()  == "true"
TAG_DISCOVER_WORKERS = int(os.environ.get("TAG_DISCOVER_WORKERS", "10"))
OCI_CONFIG_PATH = os.environ.get("OCI_CONFIG_PATH", "")
DISCARD_METRICS_FOR_UNTAGGED_RESOURCES = os.environ.get("DISCARD_METRICS_FOR_UNTAGGED_RESOURCES", "false").lower() == "true"

# Freeform tag filters used to match metrics to specific clusters/controllers.
# Values are populated from the hosting node's freeform tags during initialization.
FREEFORM_TAGS_FILTERS = {
    "cluster_name": "",
    "controller_name": ""
}

# Thread-safe counter for discarded metrics (when DISCARD_METRICS_FOR_UNTAGGED_RESOURCES is enabled)
discarded_untagged_metrics = 0
discarded_metrics_lock = Lock()

def camelCase_to_snake_case(camel_case_str: str) -> str:
    """Convert a camelCase string to snake_case.

    Args:
        camel_case_str: The camelCase string to convert.

    Returns:
        str: The converted snake_case string.
    """
    return re.sub(r'([a-z])([A-Z])', r'\1_\2', camel_case_str).lower()


@lfu_cache(maxsize=10240)
def fetch_resource_tags(namespace: str, tags: str) -> Dict[str, Any]:
    """Fetch resource tags and metadata from OCI API for metric enrichment.

    This function retrieves resource information from OCI based on metric tags,
    enriches it with additional metadata (e.g., Slurm hostnames), and applies
    filtering based on freeform tags when DISCARD_METRICS_FOR_UNTAGGED_RESOURCES is enabled.

    For blockstore and VCN resources, attempts to resolve the associated compute instance
    and derive Slurm hostname information from /etc/hosts.

    The function is caching the responses using an lfu_cache.

    Args:
        namespace (str): The OCI service namespace (e.g., 'oci_compute', 'oci_blockstore').
        tags (str): JSON string containing metric tags including resource identifiers.

    Returns:
        dict: Dictionary of enriched tags to add to the metric. If the metric should be
              discarded (due to missing required tags), returns {'discard': True}.
              Returns empty dict on error.
    """
    global discarded_untagged_metrics, discarded_metrics_lock
    api_resource_tags = {}
    
    try:
        metric_tags = json.loads(tags)
        resource_info, resource_additional_tags = oci_client.get_resource(namespace, metric_tags)

        if resource_info.status != 200:
            logger.error(f"API returned unexpected status code: {resource_info.status}. Response: {resource_info}")
            return api_resource_tags
        
        # Don't drop metrics for untagged buckets
        if namespace != "oci_objectstorage":
            if DISCARD_METRICS_FOR_UNTAGGED_RESOURCES:
                for k, v in FREEFORM_TAGS_FILTERS.items():
                    if not ( resource_info.data.freeform_tags.get(k, None) and resource_info.data.freeform_tags.get(k) == v ):
                        with discarded_metrics_lock:
                            discarded_untagged_metrics += 1
                        return {"discard": True}

        # Build additional tags dictionary from resource metadata
        # resource_additional_tags defines which resource attributes to include as tags
        additional_tags = {}

        for k, v in resource_additional_tags.items():
            if hasattr(resource_info.data, k):
                additional_tags[v] = getattr(resource_info.data, k)

        # Add Slurm instance details for blockstore and VNIC resources
        # These resources don't directly have hostnames, so we need to resolve
        # them through their attached compute instances
        slurm_host = ""
        instance_display_name = ""

        if namespace == "oci_blockstore":
            instance_id = None
            attachment_id = metric_tags.get("attachmentId", "")

            if "volumeattachment" in attachment_id:
                # For volume attachments, we need to find the compute instance
                # by listing all volume attachments in the compartment/AD
                volume_attachments = oci_client.handlers["oci_compute"].get_client("ComputeClient").list_volume_attachments(
                    compartment_id=resource_info.data.compartment_id,
                    availability_domain=resource_info.data.availability_domain
                )

                if volume_attachments.status == 200:
                    for entry in volume_attachments.data:
                        if entry.id == attachment_id:
                            instance_id = entry.instance_id
                            break

                # Paginate through results if not found on first page
                while volume_attachments.has_next_page and instance_id is None:
                    volume_attachments = oci_client.handlers["oci_compute"].get_client("ComputeClient").list_volume_attachments(
                        compartment_id=resource_info.data.compartment_id,
                        availability_domain=resource_info.data.availability_domain,
                        page=volume_attachments.next_page
                    )
                    if volume_attachments.status == 200:
                        for entry in volume_attachments.data:
                            if entry.id == attachment_id:
                                instance_id = entry.instance_id
                                break

            elif "instance" in attachment_id:
                # Direct instance attachment
                instance_id = attachment_id

            # Fetch instance details to get display name for Slurm resolution
            if instance_id:
                logger.debug(f"Looking up instance_id {instance_id}")
                instance_details = fetch_resource_tags("oci_compute", json.dumps({"resourceId": instance_id}))
                if instance_details:
                    instance_display_name = instance_details.get("display_name", "")
                    logger.debug(f"Instance: {instance_display_name} discovered for: {metric_tags}")

        # Process VCN resources (VNICs)
        elif namespace == "oci_vcn" and "vnic" in metric_tags.get("resourceId", ""):
            # Find the compute instance attached to this VNIC
            vnic_attachments = oci_client.handlers["oci_compute"].get_client("ComputeClient").list_vnic_attachments(
                    compartment_id=resource_info.data.compartment_id,
                    vnic_id=resource_info.data.id
                )
            if vnic_attachments.status == 200 and len(vnic_attachments.data) > 0:
                instance_id = vnic_attachments.data[0].instance_id
                logger.debug(f"Found instance_id {instance_id} for VNIC resource {resource_info.data.id}")
                instance_details = fetch_resource_tags("oci_compute", json.dumps({"resourceId": instance_id}))
                if instance_details:
                    instance_display_name = instance_details.get("display_name", "")
                    logger.debug(f"Instance: {instance_display_name} discovered for: {metric_tags}")

        # Resolve the Slurm hostname from OCI instance display name
        if instance_display_name:
            additional_tags["oci_name"] = instance_display_name
            slurm_host = _resolve_slurm_hostname(instance_display_name)
            if slurm_host:
                additional_tags["hostname"] = slurm_host
            else:
                additional_tags["hostname"] = instance_display_name

        # Merge freeform tags with additional tags, flattening nested dictionaries
        # Empty values are filtered out
        if additional_tags:
            api_resource_tags = {k: v  for k, v in
                flatten_dict({**resource_info.data.freeform_tags, **additional_tags}, sep = ".").items() if v}
        else:
            api_resource_tags = {k: v  for k, v in
                flatten_dict(resource_info.data.freeform_tags, sep = ".").items() if v}
    
    except Exception as e:
        logger.error(f"Error fetching resource tags for namespace {namespace}, tags {tags}: {traceback.format_exc()}")

    return api_resource_tags


@lfu_cache(maxsize=5192)
def _resolve_slurm_hostname(instance_display_name: str) -> str:
    """Resolve Slurm hostname from /etc/hosts by matching OCI instance display name.

    Parses /etc/hosts to find the Slurm hostname corresponding to an OCI instance
    display name. Searches within Ansible-managed blocks, prioritizing controller
    blocks over compute blocks.

    The function is caching the responses using an lfu_cache.

    Args:
        instance_display_name (str): The OCI instance display name to resolve.

    Returns:
        str: The resolved Slurm hostname, or empty string if not found.

    Note:
        This function looks for entries within:
        1. '# BEGIN/END ANSIBLE MANAGED BLOCK controller' sections (priority)
        2. '# BEGIN/END ANSIBLE MANAGED BLOCK' sections (fallback)
    """
    try:
        with open("/etc/hosts", "r") as hosts_file:
            lines = hosts_file.readlines()

        in_managed_block = False
        in_controller_block = False

        for line in lines:
            # Track which Ansible-managed block we're in
            if line.startswith("# BEGIN ANSIBLE MANAGED BLOCK controller"):
                in_controller_block = True
            elif line.startswith("# END ANSIBLE MANAGED BLOCK controller"):
                in_controller_block = False
            elif line.startswith("# BEGIN ANSIBLE MANAGED BLOCK") and "controller" not in line:
                in_managed_block = True
            elif line.startswith("# END ANSIBLE MANAGED BLOCK") and "controller" not in line:
                in_managed_block = False
            # In controller blocks, the hostname is the last whitespace-separated token
            elif in_controller_block:
                if line.strip() and instance_display_name in line:
                    groups = re.findall(r"\S+", line.strip())
                    return groups[-1] if groups else ""
            # In regular managed blocks, the hostname is the second token
            elif in_managed_block:
                if line.strip() and instance_display_name in line:
                    groups = re.findall(r"\S+", line.strip())
                    return groups[1] if len(groups) > 1 else ""
                    
    except Exception as e:
        logger.error(f"Error processing /etc/hosts: {traceback.format_exc()}")

    return ""

def metric_to_stdout(fn: Future[Tuple[Dict[str, Any], Dict[str, Any]]]) -> None:
    """Callback function to output enriched metrics to stdout.

    This function is called when a resource tag enrichment job completes.
    It constructs an InfluxDB line protocol metric with enriched tags and
    outputs it to stdout for Telegraf to process.

    Args:
        fn: A concurrent.futures.Future object representing the completed job.

    Note:
        Metrics marked for discard ({'discard': True}) are silently skipped.
    """
    if fn.done():
        error = fn.exception()
        if error:
            logger.error(f'Request to enrich metric with tags returned the error: {error}.')
        else:
            oci_metric, oci_tags = fn.result()

            # Skip metrics marked for discard (missing required tags)
            if oci_tags.get("discard", False):
                return

            # Construct the InfluxDB line protocol metric
            # Convert measurement name and tag keys from camelCase to snake_case
            metric = Metric(camelCase_to_snake_case(oci_metric["measurement"]))
            metric.with_timestamp(oci_metric["time"])

            # Add original metric tags (converted to snake_case)
            for k, v in oci_metric.get("tags", {}).items():
                metric.add_tag(camelCase_to_snake_case(k), v)

            # Add enriched OCI resource tags (converted to snake_case)
            for k, v in oci_tags.items():
                metric.add_tag(camelCase_to_snake_case(k), v)

            # Add metric field values
            for k, v in oci_metric.get("fields", {}).items():
                metric.add_value(k, v)

            logger.debug(f"Constructed metric: {metric}")
            print(metric, file=sys.stdout, flush=True)


def fetch_resource(namespace: str, metric: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Fetch resource tags for a given metric.

    Args:
        namespace: The OCI service namespace for the metric.
        metric: The metric dictionary containing tags.

    Returns:
        A tuple of (metric, resource_tags) where resource_tags is the
        enriched tag dictionary from OCI API.
    """
    tags = metric.get("tags", {})
    resource_tags = fetch_resource_tags(namespace, json.dumps(tags))
    return metric, resource_tags


def main(oci_config: Dict[str, Any], oci_signer: Any) -> None:
    """Main function that processes metrics with tag enrichment enabled.

    Initializes the OCI client with retry strategy, sets up a thread pool for
    parallel tag enrichment, and processes metrics from stdin. Each metric is
    enriched with resource tags from the OCI API before being output to stdout.

    Args:
        oci_config: OCI configuration dictionary (empty for instance principals).
        oci_signer: OCI authentication signer (config-based or instance principal).
    """
    global oci_client
    logger.info("Initializing main loop.")

    # Configure retry strategy
    oci_retry_strategy = RetryStrategyBuilder(
        max_attempts_check=True,
        max_attempts=3,
        retry_max_wait_between_calls_seconds=3,
        service_error_check=True,
        service_error_retry_on_any_5xx=True,
        service_error_retry_config={
            429: []
        },
        backoff_type=BACKOFF_FULL_JITTER_EQUAL_ON_THROTTLE_VALUE
    ).get_retry_strategy()

    logger.debug("Setting up OCI API clients.")
    logger.debug("Setting up ThreadPoolExecutor.")

    # Initialize thread pool
    executor = ThreadPoolExecutor(TAG_DISCOVER_WORKERS)
    
    #Ensure the oci_client is created
    oci_client = OCIMetaClient(config=oci_config, signer=oci_signer, retry_strategy=oci_retry_strategy)

    logger.info("Entering the main loop with metric tag enrichment.")

    # Start background thread to monitor cache utilization
    stat_thread = Thread(target=cache_status, daemon=True)
    stat_thread.start()

    try:
        while True:
            try:
                # Process metrics from stdin line by line
                for entry in sys.stdin:
                    try:
                        # Parse the InfluxDB line protocol metric
                        metric = parse_line(entry)
                        namespace = metric.get("tags", {}).get("namespace", "")

                        if not namespace:
                            logger.warning("Namespace is null, skipping metric")
                            continue

                        # Submit async job to fetch resource tags and enrich metric
                        job = executor.submit(fetch_resource, namespace, metric)
                        # Register callback to output enriched metric when complete
                        job.add_done_callback(metric_to_stdout)
                    except Exception as e:
                        logger.error(f"Couldn't process the input {entry}: {traceback.format_exc()}")

                break
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, exiting...")
                break
    finally:
        logger.info("Shutting down executor...")
        executor.shutdown(wait=True, cancel_futures=False)
        logger.info("Shutdown complete.")

def main_no_tags() -> None:
    """Main function that processes metrics without tag enrichment (debug mode).

    Reads metrics from stdin, converts tag names from camelCase to snake_case,
    and outputs them to stdout without any OCI API enrichment. Useful for
    debugging or when tag enrichment is not required.
    """
    logger.info("Entering the main loop without metric tag enrichment.")

    while True:
        try:
            for entry in sys.stdin:
                try:
                    # Parse metric from input
                    metric_from_input = parse_line(entry)

                    # Construct output metric with snake_case conversion
                    metric = Metric(camelCase_to_snake_case(metric_from_input["measurement"]))
                    metric.with_timestamp(metric_from_input["time"])

                    # Add tags (converted to snake_case)
                    for k, v in metric_from_input.get("tags", {}).items():
                        metric.add_tag(camelCase_to_snake_case(k), v)

                    # Add field values
                    for k, v in metric_from_input.get("fields", {}).items():
                        metric.add_value(k, v)

                    logger.debug(f"Constructed metric: {metric}")
                    print(metric, file=sys.stdout, flush=True)

                except Exception as e:
                    logger.error(f"Couldn't process the input {entry}: {traceback.format_exc()}")
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, exiting...")
            break


def handle_sighup(signum: int, frame: Any) -> None:
    """Signal handler for SIGHUP that triggers graceful shutdown.

    Args:
        signum: The signal number received.
        frame: The current stack frame (unused, part of signal handler signature).
    """
    logger.info("Received SIGHUP, exiting...")
    sys.exit(0)

def fetch_instance_freeform_tags() -> Optional[Dict[str, Any]]:
    """
    Fetch instance freeform tags from Oracle Cloud IMDS endpoint.

    Returns:
        Instance freeform tags as JSON object, or None if request fails
    """
    try:
        req = Request('http://169.254.169.254/opc/v2/instance/')
        req.add_header('Authorization', 'Bearer Oracle')
        content = urlopen(req).read()

        instance_metadata = json.loads(content.decode('utf-8'))
        return instance_metadata.get("freeformTags", {})
    except Exception as e:
        logger.error(f"Failed to get instance freeform tags: {traceback.format_exc()}")
        return None

def cache_status() -> None:
    """Background thread function that periodically logs cache statistics.

    Reports cache utilization for the two main LFU caches and the count of
    discarded metrics. Runs in an infinite loop with 5-minute intervals.
    """
    global discarded_untagged_metrics, discarded_metrics_lock
    while True:
        logger.info(f"OCI resource tags lru_cache utilization: {fetch_resource_tags.cache.currsize}/{fetch_resource_tags.cache.maxsize}")
        logger.info(f"OCI instance info lru_cache utilization: {_resolve_slurm_hostname.cache.currsize}/{_resolve_slurm_hostname.cache.maxsize}")
        logger.info(f"Discarded untagged metrics in the last five minutes: {discarded_untagged_metrics}")
        with discarded_metrics_lock:
            discarded_untagged_metrics = 0
        time.sleep(300)

if __name__ == "__main__":
    # Setup logging to stderr with Telegraf-compatible format
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    formatter = TelegrafFormatter(fmt='%(asctime)s - %(name)s - %(threadName)s - %(message)s', datefmt='%Y-%m-%dT%H:%M:%S')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger = logging.getLogger(__name__)

    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGHUP, handle_sighup)

    if ENRICH_METRICS:
        # Attempt to load OCI credentials from config file
        auth = False
        try:
            from oci.config import from_file
            if OCI_CONFIG_PATH:
                logger.info(f"OCI CONFIG PATH: {OCI_CONFIG_PATH}")
                config = from_file(file_location=OCI_CONFIG_PATH, profile_name="DEFAULT")
            else:
                config = from_file(profile_name="DEFAULT")

            from oci import Signer
            signer = Signer.from_config(config)
            auth = True
        except Exception as e:
            logger.error(f'Failed to load profile and signer from the OCI config file: {e}')


        if not auth:
            # Fallback to instance principals if config file auth failed
            logger.info('Attempting to use instance_principal...')
            try:
                from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
                config = {}
                signer = InstancePrincipalsSecurityTokenSigner()
            except Exception as e:
                logger.error(f"Failed to load instance_principal signer. No supported signer found: {traceback.format_exc()}")
                sys.exit(1)

        # Fetch this node's freeform tags to populate cluster filters
        node_tags = fetch_instance_freeform_tags()
        if node_tags:
            for key in FREEFORM_TAGS_FILTERS.keys():
                if key in node_tags.keys():
                    FREEFORM_TAGS_FILTERS[key] = node_tags[key]

        # Remove empty filter keys (tags that don't exist on this node)
        for key, value in tuple(FREEFORM_TAGS_FILTERS.items()):
            if value == "":
                FREEFORM_TAGS_FILTERS.pop(key)

        main(config, signer)
    else:
        # Run in pass-through mode without enrichment
        main_no_tags()
