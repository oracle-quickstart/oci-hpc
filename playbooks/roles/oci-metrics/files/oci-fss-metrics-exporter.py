import oci
from datetime import datetime, timedelta, timezone
from prometheus_client import start_http_server, Gauge
import logging
import re
import time
import requests

signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
monitoring = oci.monitoring.MonitoringClient({}, signer=signer)
file_storage_client = oci.file_storage.FileStorageClient({}, signer=signer)
prometheus_metrics = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_compartment_id():
    url = "http://169.254.169.254/opc/v1/instance/"
    headers = {
        "Authorization": "Bearer Oracle"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()['compartmentId']

def initialize_metrics(
    monitoring: oci.monitoring.MonitoringClient,
    file_storage_client: oci.file_storage.FileStorageClient,
    compartment_id: str
) -> dict:
    oci_data = {
        'metrics': [],
        'mount_targets': {},
        'filesystems': {}
    }
    
    try:
        # Fetch metrics
        paginated_response = oci.pagination.list_call_get_all_results(
            monitoring.list_metrics,
            compartment_id,
            oci.monitoring.models.ListMetricsDetails(namespace="oci_filestorage")  
        ).data
        
        # Store metrics
        oci_data['metrics'] = [metric.name for metric in paginated_response]
        logger.info(f"Found {len(oci_data['metrics'])} filesystem metrics")
        print(oci_data['metrics'])
        # Process mount targets     
        for resp in paginated_response:
            try:
                if resp.dimensions.get("resourceType") == "filesystem":
                    mount_target_id = resp.dimensions["mountTargetId"]
                    file_system_id = resp.dimensions["resourceId"]
                elif resp.dimensions.get("resourceType") == "mountTarget":
                    mount_target_id = resp.dimensions["resourceId"]
                    
                if mount_target_id not in oci_data['mount_targets']:
                    mount_target = file_storage_client.get_mount_target(mount_target_id=mount_target_id).data
                    oci_data['mount_targets'][mount_target_id] = {
                        "name": mount_target.display_name,
                        "ad": "-".join(mount_target.availability_domain.split("-")[1:]).lower()
                    }
                if file_system_id not in oci_data['filesystems']:
                    file_system = file_storage_client.get_file_system(file_system_id=file_system_id).data
                    oci_data['filesystems'][file_system_id] = {
                        "name": file_system.display_name,
                        "ad": "-".join(file_system.availability_domain.split("-")[1:]).lower()
                    }
            except Exception as e:
                logger.error(f"Failed to process mount target {mount_target_id}: {str(e)}")
                continue

        logger.info(f"Processed {len(oci_data['mount_targets'])} mount target metadata lookup")
        logger.info(f"Processed {len(oci_data['filesystems'])} file system metadata lookup")
        return oci_data
        
    except Exception as e:
        logger.error(f"Failed to initialize OCI data: {str(e)}")
        raise

def fetch_and_push_metric_data(monitoring: oci.monitoring.MonitoringClient, 
                     compartment_id: str,
                     metrics: dict):    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=5)

    for metric_name in metrics["metrics"]:
        try:
            metric_details = oci.monitoring.models.SummarizeMetricsDataDetails(
                namespace="oci_filestorage",
                query=f"{metric_name}[5m].avg()",
                start_time=start_time,
                end_time=end_time,
                resolution="5m"
            )

            response = monitoring.summarize_metrics_data(
                compartment_id=compartment_id,
                summarize_metrics_data_details=metric_details
            )
            for metric_data in response.data:      
                if metric_name not in prometheus_metrics:
                    description = metric_data.metadata['description'] + "(" + metric_data.metadata['unit'] + ")"
                    gauge = Gauge(
                        name=f"oci_{metric_name}",
                        documentation=description,
                        labelnames=['mount_target', 'file_system', 'availability_domain', 'resource_type', 'size'],
                    )
                    prometheus_metrics[metric_name] = gauge
                mount_target_id = ""
                if 'mountTargetId' in metric_data.dimensions:
                    mount_target_id = metric_data.dimensions['mountTargetId']
                else:
                    mount_target_id = metric_data.dimensions['resourceId']   
                if 'size' in metric_data.dimensions:
                    size = metric_data.dimensions['size']
                else:
                    size = "none"
                if metric_data.dimensions['resourceType'] == "filesystem":
                    prometheus_metrics[metric_name].labels(
                        mount_target=metrics["mount_targets"][mount_target_id]['name'],
                        file_system=metrics["filesystems"][metric_data.dimensions['resourceId']]['name'],
                        availability_domain=metrics["mount_targets"][mount_target_id]['ad'],
                        resource_type=metric_data.dimensions['resourceType'],
                        size=size
                    ).set(metric_data.aggregated_datapoints[0].value)
                else:
                    prometheus_metrics[metric_name].labels(
                        mount_target=metrics["mount_targets"][mount_target_id]['name'],
                        availability_domain=metrics["mount_targets"][mount_target_id]['ad'],
                        resource_type=metric_data.dimensions['resourceType'],
                        file_system="none",
                        size=size
                    ).set(metric_data.aggregated_datapoints[0].value) 
                # To work around OCI metrics api complaining about too many requests
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed to fetch metric {metric_name}: {str(e)}")
            continue

if __name__ == "__main__":
    compartment_id = get_compartment_id()
    metrics = initialize_metrics(monitoring=monitoring, file_storage_client=file_storage_client, compartment_id=compartment_id)
    start_http_server(9200)
    while True:
        fetch_and_push_metric_data(monitoring, compartment_id, metrics)
        time.sleep(60)


