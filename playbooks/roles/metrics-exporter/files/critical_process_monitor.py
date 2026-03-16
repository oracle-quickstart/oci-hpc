import time
import subprocess
from prometheus_client import start_http_server, Gauge

services = ["sssd", "sshd", "systemd-resolved", "nvidia-fabricmanager", "customMetrics", "node_exporter"] 
interval = 60

service_up_metric = Gauge("service_up", "Service availability status (1 = running, 0.5 = running with errors, 0 = failed)", ['hostname', 'service'])

def check_service_status():    
    try:
        hostname = subprocess.getoutput("hostname")
        for service in services:
            result = subprocess.run(["systemctl", "is-enabled", service], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if result.returncode == 0:
                result = subprocess.run(["systemctl", "status", service], stdout=subprocess.PIPE)
                output = result.stdout.decode('utf-8')
                if output.find("active (running)") > 0:
                    service_up_metric.labels(hostname=hostname, service=service).set(1)
                    if service=="nvidia-fabricmanager" and output.find("error occurred") > 0:
                       service_up_metric.labels(hostname=hostname, service=service).set(0.5)
                else:
                    service_up_metric.labels(hostname=hostname, service=service).set(0)
    except Exception as e:
        print(f"Error checking service status: {e}")
        service_up_metric.labels(hostname=hostname, service=service).set(0)

def main():
    start_http_server(9700)

    # Main loop to periodically check the service status
    while True:
        check_service_status()
        time.sleep(interval)

if __name__ == "__main__":
    main()

