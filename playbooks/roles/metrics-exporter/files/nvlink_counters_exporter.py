from prometheus_client import start_http_server, Gauge
import time
import subprocess
from io import StringIO
import json
import re
gpu_data = {}
link_data = {}
gpu_id = None
gpu = None

data_tx_kib = Gauge('nvlink_data_tx_kib', 'Total data in KiB transmitted', ['hostname', 'gpu', "link"])
data_rx_kib = Gauge('nvlink_data_rx_kib', 'Total data in KiB received', ['hostname', 'gpu', "link"])
raw_tx_kib = Gauge('nvlink_raw_tx_kib', 'Total raw bytes in KiB transmitted', ['hostname', 'gpu', "link"])
raw_rx_kib = Gauge('nvlink_raw_rx_kib', 'Total raw bytes in KiB received', ['hostname', 'gpu', "link"])

def get_nvlink_metrics():
    hostname = subprocess.getoutput("hostname")
    metrics_raw = StringIO(subprocess.getoutput("/usr/bin/nvidia-smi nvlink -gt rd"))
    for line in metrics_raw:
        line = line.strip()
        if line.startswith("GPU"):
            gpu_match = re.match(r"GPU (\d+): (.+?) \(UUID: (.+?)\)", line.strip())
            if gpu_match:
                gpu_id = gpu_match.group(1)
                gpu_model = gpu_match.group(2)
                gpu_uuid = gpu_match.group(3)
                gpu = f"GPU_{gpu_id}"
                gpu_data[gpu] = {
                    "model": gpu_model,
                    "uuid": gpu_uuid
                }
                link_data[gpu] = {}
        elif line.startswith("Link") and gpu is not None:
            line = line.strip()
            data_tx_match = re.match(r"Link (\d+): Data Tx: (\d+) KiB", line)
            data_rx_match = re.match(r"Link (\d+): Data Rx: (\d+) KiB", line)
            raw_tx_match = re.match(r"Link (\d+): Raw Tx: (\d+) KiB", line)
            raw_rx_match = re.match(r"Link (\d+): Raw Rx: (\d+) KiB", line)
            if data_tx_match:
                link_id = data_tx_match.group(1)
                data_tx = int(data_tx_match.group(2))
                data_tx_kib.labels(hostname=hostname, gpu=gpu_id, link=link_id).set(data_tx)
                if link_id in link_data[gpu]:
                   link_data[gpu][link_id]["data_tx_kib"]=data_tx
                else:
                   link_data[gpu][link_id]={}
                   link_data[gpu][link_id]["data_tx_kib"]=data_tx
            if data_rx_match:
                link_id = data_rx_match.group(1)
                data_rx = int(data_rx_match.group(2))
                data_rx_kib.labels(hostname=hostname, gpu=gpu_id, link=link_id).set(data_rx)
                if link_id in link_data[gpu]:
                   link_data[gpu][link_id]["data_rx_kib"]=data_rx
                else:
                   link_data[gpu][link_id]={}
                   link_data[gpu][link_id]["data_rx_kib"]=data_rx
            if raw_tx_match:
                link_id = raw_tx_match.group(1)
                raw_tx = int(raw_tx_match.group(2))
                raw_tx_kib.labels(hostname=hostname, gpu=gpu_id, link=link_id).set(raw_tx)
                if link_id in link_data[gpu]:
                   link_data[gpu][link_id]["raw_tx_kib"]=raw_tx
                else:
                   link_data[gpu][link_id]={}
                   link_data[gpu][link_id]["raw_tx_kib"]=raw_tx
            if raw_rx_match:
                link_id = raw_rx_match.group(1)
                raw_rx = int(raw_rx_match.group(2))
                raw_rx_kib.labels(hostname=hostname, gpu=gpu_id, link=link_id).set(raw_rx)
                if link_id in link_data[gpu]:
                   link_data[gpu][link_id]["raw_rx_kib"]=raw_rx
                else:
                   link_data[gpu][link_id]={}
                   link_data[gpu][link_id]["raw_rx_kib"]=raw_rx
if __name__ == '__main__':
    # Start up the server to expose the metrics.
    start_http_server(9600)
    # Generate NVLink metrics every 10 seconds
    while True:
        get_nvlink_metrics()
        time.sleep(10)

