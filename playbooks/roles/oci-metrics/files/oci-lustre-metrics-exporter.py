import oci
import requests
from datetime import datetime, timedelta, timezone
from prometheus_client import start_http_server, Gauge
import logging
import time

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics dictionary
prometheus_metrics = {}
resource_labels = {}

# OCI Auth
signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
monitoring = oci.monitoring.MonitoringClient({}, signer=signer)
lustre_client = oci.lustre_file_storage.LustreFileStorageClient({}, signer=signer)

# Get Compartment OCID
def get_compartment_id():
    url = "http://169.254.169.254/opc/v1/instance/"
    headers = {"Authorization": "Bearer Oracle"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["compartmentId"]

# Fetch all unique Lustre metrics
def list_lustre_metrics(monitoring, compartment_id):
    logger.info("Fetching Lustre metric list...")
    response = oci.pagination.list_call_get_all_results(
        monitoring.list_metrics,
        compartment_id,
        oci.monitoring.models.ListMetricsDetails(namespace="oci_lustrefilesystem")
    )
    return sorted(set(metric.name for metric in response.data))

# Register metric in Prometheus registry
def get_or_create_gauge(metric_name, description):
    if metric_name not in prometheus_metrics:
        prometheus_metrics[metric_name] = Gauge(
            f"oci_{metric_name}",
            description,
            ['resource_name', 'client_name', 'capacity_type', 'operation_type', 'target_type']
        )
    return prometheus_metrics[metric_name]

# Fetch and expose metric values
def push_metrics(monitoring, compartment_id, metric_names):
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=5)

    for metric_name in metric_names:
        try:
            request = oci.monitoring.models.SummarizeMetricsDataDetails(
                namespace="oci_lustrefilesystem",
                query=f"{metric_name}[5m].avg()",
                start_time=start_time,
                end_time=end_time,
                resolution="5m"
            )
            response = monitoring.summarize_metrics_data(
                compartment_id=compartment_id,
                summarize_metrics_data_details=request
            )

            for data in response.data:
                dim = data.dimensions
                metadata = data.metadata
                                
                labels = {
                    'resource_name': dim.get('resourceName', 'none'),
                    'client_name': dim.get('clientName', 'none'),
                    'capacity_type': dim.get('capacityType', 'none'),
                    'operation_type': dim.get('operationType', 'none'),
                    'target_type' : dim.get('targetType', 'none')
                }

                description = metadata.get('description', f"Lustre metric {metric_name}")
                units = metadata.get('units', 'no-unit')
                gauge = get_or_create_gauge(metric_name, f"{description} ({units})")

                if data.aggregated_datapoints:
                  gauge.labels(**labels).set(data.aggregated_datapoints[0].value)

            time.sleep(0.3)

        except Exception as e:
            logger.error(f"Failed to fetch metric {metric_name}: {str(e)}")

if __name__ == "__main__":
    compartment_id = get_compartment_id()
    metrics = list_lustre_metrics(monitoring, compartment_id)
    logger.info(f"Discovered Lustre Metrics: {metrics}")
    start_http_server(9200)
    while True:
         push_metrics(monitoring, compartment_id, metrics)
         time.sleep(60)