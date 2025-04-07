import oci
from datetime import datetime, timedelta, timezone
from prometheus_client import start_http_server, Gauge
import logging
import re
import time
import requests

signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
monitoring = oci.monitoring.MonitoringClient({}, signer=signer)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

prometheus_metrics = {}
oci_metric_names = {}

def get_compartment_id():
    url = "http://169.254.169.254/opc/v1/instance/"
    headers = {
        "Authorization": "Bearer Oracle"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()['compartmentId']

def mixed_case_to_underline(text):
  return re.sub(r"([a-z])([A-Z])", r"\1_\2", text).lower()

def get_gpu_name(instance_name, hosts_file='/etc/hosts'):
    with open(hosts_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if instance_name in line:
                parts = line.split()                
                if len(parts) >= 2:
                    return parts[1]
    return None

def initialize_metrics(monitoring: oci.monitoring.MonitoringClient, compartment_id: str) -> list:
    metrics = oci.pagination.list_call_get_all_results(
        monitoring.list_metrics,
        compartment_id,
        oci.monitoring.models.ListMetricsDetails(namespace="rdma_infrastructure_health")
    ).data
    return metrics

def fetch_and_push_metric_data(monitoring: oci.monitoring.MonitoringClient, compartment_id: str, metrics: dict):
    for each_metric in metrics:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(minutes=1)        
        metric_details = oci.monitoring.models.SummarizeMetricsDataDetails(
            namespace="rdma_infrastructure_health",
            query=f"{each_metric}[1m].mean()",
            start_time=start_time,
            end_time=end_time,
            resolution="1m"
        )
        response = monitoring.summarize_metrics_data(
            compartment_id=compartment_id,
            summarize_metrics_data_details=metric_details
        )
        for metric_data in response.data:
            metric_name = mixed_case_to_underline(metric_data.name)
            if metric_name not in prometheus_metrics:
                description = metric_data.metadata['displayName'] + "(" + metric_data.metadata['unit'] + ")"
                gauge = Gauge(
                    name=f"oci_{metric_name}",
                    documentation=description,
                    labelnames=['device_name', 'oci_name', 'hostname'],
                )
                prometheus_metrics[metric_name] = gauge
            prometheus_metrics[metric_name].labels(
                device_name=metric_data.dimensions['deviceName'],
                oci_name=metric_data.dimensions['resourceDisplayName'],
                hostname=get_gpu_name(metric_data.dimensions['resourceDisplayName'])).set(metric_data.aggregated_datapoints[0].value)                 
            time.sleep(0.5)

if __name__ == "__main__":
    compartment_id = get_compartment_id()
    metrics = initialize_metrics(monitoring=monitoring, compartment_id=compartment_id)
    unique_fault_metrics = {metric.name: metric for metric in metrics if 'Fault' in metric.name}
    logger.info(f"Found {len(unique_fault_metrics)} rdma fault metrics")
    start_http_server(9300)
    while True:
        fetch_and_push_metric_data(monitoring, compartment_id, unique_fault_metrics)
        time.sleep(60)