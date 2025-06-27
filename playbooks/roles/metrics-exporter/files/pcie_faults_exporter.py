from datetime import datetime, timedelta, timezone
from prometheus_client import start_http_server, Gauge
import logging
import os
import re
import time
import pyudev

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

rdma_pcie_mapping = {}
nvme_pcie_mapping = {}
gpu_pcie_mapping = {}

pcie_aer_correctable_error_count = Gauge('pcie_aer_correctable_error_count', 'PCI AER correctable error count',
                         ['hostname', 'device', 'device_type', 'pcie'])
pcie_aer_fatal_error_count = Gauge('pcie_aer_fatal_error_count', 'PCI AER fatal error count',
                         ['hostname', 'device', 'device_type', 'pcie'])
pcie_aer_nonfatal_error_count = Gauge('pcie_aer_nonfatal_error_count', 'PCI AER non-fatal error count',
                         ['hostname', 'device', 'device_type', 'pcie'])
pcie_bus_linkwidth_status = Gauge('pcie_bus_linkwidth_status', 'PCI Link Width mismatch detected (1=error, 0=ok)',
                         ['hostname', 'device', 'device_type', 'pcie'])
pcie_bus_inaccessible_status = Gauge('pcie_bus_inaccessible_status', 'PCI Bus Inaccessible (1=error, 0=ok)',
                        ['hostname', 'device', 'device_type', 'pcie'])

def read_and_parse_sys_file(file_path, key=""):
    try:
        with open(file_path, 'r') as file:
            content = file.read().strip()
            if key == "":
                return int(re.search(r"(\d+)", content).group(1))
            else:
                for line in content.splitlines():
                    if line.startswith(key):
                        parts = line.split()
                        if len(parts) > 1:
                            return int(parts[1])  
        logger.info(f"Key '{key}' not found in file: {file_path}")
        return None
    except FileNotFoundError:
        logger.info(f"File not found: {file_path}")
        return None
    except ValueError as e:
        logger.info(f"Failed to parse integer value for key '{key}' in file {file_path}: {e}")
        return None
    except Exception as e:
        logger.info(f"Error reading file {file_path}: {e}")
        return None

def get_pci_addresses(subsystem):
    context = pyudev.Context()
    devices = {}
    for device in context.list_devices(subsystem=subsystem):
        device_sys_path = device.sys_path
        pcie_path = device_sys_path.split(f"/{subsystem}")[0]
        pci_address = device_sys_path.split('/')[-3]
        path_len = len(pcie_path.split('/'))
        devices[device.sys_name] = {'pcie_addr': pci_address, 'pcie_path': pcie_path, 'path_len': path_len}
    return devices

def get_gpu_pci_addresses():
    import subprocess
    devices = {}
    try:
        out = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=pci.bus_id",
            "--format=csv,noheader,nounits"
        ], stderr=subprocess.DEVNULL).decode().strip()
        
        bus_ids = [line.strip() for line in out.splitlines() if line.strip()]
        
        for gpu_index, bus_id in enumerate(bus_ids):
            normalized_bus_id = bus_id.lower()
            if normalized_bus_id.startswith('0000:'):
                normalized_bus_id = normalized_bus_id[5:]
            else:
                normalized_bus_id = normalized_bus_id[4:]
            
            device_sys_path = f"/sys/bus/pci/devices/{normalized_bus_id}"
            gpu_device_name = f"nvidia{gpu_index}"
            devices[gpu_device_name] = {
                'pcie_addr': normalized_bus_id, 
                'pcie_path': device_sys_path, 
                'path_len': len(device_sys_path.split('/'))
            }
    except subprocess.CalledProcessError:
        logger.info("nvidia-smi failed or no NVIDIA GPUs found")
    except Exception as e:
        logger.info(f"Error getting GPU PCI addresses: {e}")
    
    return devices

def collect_pcie_metrics(hostname, device_mapping, device_type):
    for device in device_mapping.keys():
        pcimap = device_mapping[device]
        correctable_error_count = read_and_parse_sys_file(pcimap['pcie_path'] + "/aer_dev_correctable", "TOTAL_ERR_COR")
        fatal_error_count = read_and_parse_sys_file(pcimap['pcie_path'] + "/aer_dev_fatal", "TOTAL_ERR_FATAL")
        nonfatal_error_count = read_and_parse_sys_file(pcimap['pcie_path'] + "/aer_dev_nonfatal", "TOTAL_ERR_NONFATAL")
        current_link_speed = read_and_parse_sys_file(pcimap['pcie_path'] + "/current_link_speed")
        current_link_width = read_and_parse_sys_file(pcimap['pcie_path'] + "/current_link_width")
        if current_link_speed is None or current_link_width is None:
            pcie_bus_inaccessible_status.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(1)
        else:
            pcie_bus_inaccessible_status.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(0)

        if device_type == "RDMA" and pcimap['path_len']==14:
           if current_link_width == current_link_speed:
              pcie_bus_linkwidth_status.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(0)
           else:
              pcie_bus_linkwidth_status.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(1)
        elif device_type == "GPU":
           if current_link_width and current_link_speed:
              pcie_bus_linkwidth_status.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(0)
           else:
              pcie_bus_linkwidth_status.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(1)
        
        pcie_aer_correctable_error_count.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(correctable_error_count)
        pcie_aer_fatal_error_count.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(fatal_error_count)
        pcie_aer_nonfatal_error_count.labels(hostname=hostname, device=device, device_type=device_type, pcie=pcimap['pcie_addr']).set(nonfatal_error_count)

if __name__ == "__main__":
    hostname = os.uname().nodename
    rdma_pcie_mapping = get_pci_addresses("infiniband")
    nvme_pcie_mapping = get_pci_addresses("nvme")
    gpu_pcie_mapping = get_gpu_pci_addresses()
    start_http_server(9700)
    while True:
        collect_pcie_metrics(hostname, nvme_pcie_mapping, "NVME")
        collect_pcie_metrics(hostname, rdma_pcie_mapping, "RDMA")
        collect_pcie_metrics(hostname, gpu_pcie_mapping, "GPU")
        time.sleep(60)

