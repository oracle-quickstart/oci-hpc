local g = import './g.libsonnet';
local variables = import './multi-node-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('Multi-Node Metrics')
+ g.dashboard.withUid('multi-node-metrics')
+ g.dashboard.withDescription(|||
  Multi-Node Metrics Dashboard for cluster comparison
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster_name,
  variables.hostname,
  variables.oci_name,
  variables.device,
  variables.fstype,
  variables.mountpoint,
  variables.fss_mount,
  variables.export  
])
+ g.dashboard.withPanels([
    timeseriesPanel(
      'CPU Utilization by Node',
      'ceil(avg by (hostname) (rate(node_cpu_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name", mode!~"idle"}[5m])) * 100)',
      '{{ hostname }}',
      'percent',
      {w:12, h:8, x:0, y:0}
    ),
    timeseriesPanel(
      'Memory Utilization by Node',
      'ceil((1 - (node_memory_MemAvailable_bytes{hostname=~"$hostname",oci_name=~"$oci_name"}/node_memory_MemTotal_bytes{hostname=~"$hostname",oci_name=~"$oci_name"}))*100)',
      '{{ hostname }}',
      'percent',
      {w:12, h:8, x:12, y:0}
    ),
    timeseriesPanel(
      'Disk Read Throughput by Node',
      'avg by (hostname) (irate(node_disk_read_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:12, h:8, x:0, y:8}
    ),
    timeseriesPanel(
      'Disk Write Throughput by Node',
      'avg by (hostname) (irate(node_disk_written_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:12, h:8, x:12, y:8}
    ),
    timeseriesPanel(
      'NFS Read Throughput',
      'rate(node_mountstats_nfs_total_read_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{hostname}}:{{export}}',
      'Bps',
      {w:12, h:8, x:0, y:16}
    ),
    timeseriesPanel(
      'NFS Write Throughput',
      'rate(node_mountstats_nfs_total_write_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{hostname}}:{{export}}',
      'Bps',
      {w:12, h:8, x:12, y:16}
    ),
    timeseriesPanel(
      'NFS Metadata IOPS',
      'sum by(oci_name, hostname) (rate(node_mountstats_nfs_operations_requests_total{hostname=~"$hostname", oci_name=~"$oci_name", operation!~"READ|WRITE"}[5m]))',
      '{{hostname}}',
      'iops',
      {w:12, h:8, x:0, y:24}
    ),    
    timeseriesPanel(
      'NFS Read/Write IOPS',
      'sum by(oci_name, hostname) (rate(node_mountstats_nfs_operations_requests_total{hostname=~"$hostname", oci_name=~"$oci_name", operation=~"READ|WRITE"}[5m]))',
      '{{hostname}}',
      'iops',
      {w:12, h:8, x:12, y:24}
    ),
    timeseriesPanel(
      'NFS Request Time',
      'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_request_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{hostname}}:{{export}}',
      'cps',
      {w:12, h:8, x:0, y:32}
    ),
    timeseriesPanel(
      'NFS Response Time',
      'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_response_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{hostname}}:{{export}}',
      's',
      {w:12, h:8, x:12, y:32}
    ),    
    timeseriesPanel(
      'Network RX by Node',
      'avg by (hostname) (rate(node_network_receive_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device!~"lo|docker.*|rdma.*"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:12, h:8, x:0, y:40}
    ),
    timeseriesPanel(
      'Network TX by Node',
      'avg by (hostname) (rate(node_network_transmit_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device!~"lo|docker.*|rdma.*"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:12, h:8, x:12, y:40}
    ),
    // GPU Metrics Time Series
    timeseriesPanel(
      'GPU Temperature by Node',
      'avg by (Hostname) (DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'celsius',
      {w:8, h:8, x:0, y:48}
    ),
    timeseriesPanel(
      'GPU Power Usage by Node',
      'avg by (Hostname) (DCGM_FI_DEV_POWER_USAGE{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'watts',
      {w:8, h:8, x:8, y:48}
    ),
    timeseriesPanel(
      'GPU Utilization by Node',
      'avg by (Hostname) (DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'percent',
      {w:8, h:8, x:16, y:48}
    ),
    timeseriesPanel(
      'GPU Memory Temperature by Node',
      'avg by (Hostname) (DCGM_FI_DEV_MEMORY_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'celsius',
      {w:8, h:8, x:0, y:56}
    ),
    timeseriesPanel(
      'GPU SM Clock by Node',
      'avg by (Hostname) (DCGM_FI_DEV_SM_CLOCK{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'hertz',
      {w:8, h:8, x:8, y:56}
    ),
    timeseriesPanel(
      'GPU Memory Copy Utilization by Node',
      'avg by (Hostname) (DCGM_FI_DEV_MEM_COPY_UTIL{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'percent',
      {w:8, h:8, x:16, y:56}
    ),
    timeseriesPanel(
      'NVLink Combined B/W by Node',
      'avg by (hostname) (sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024)',
      '{{ hostname }}',
      'Bps',
      {w:8, h:8, x:0, y:64}
    ),
    timeseriesPanel(
      'NVLink TX B/W by Node',
      'avg by (hostname) (sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024)',
      '{{ hostname }}',
      'Bps',
      {w:8, h:8, x:8, y:64}
    ),
    timeseriesPanel(
      'NVLink RX B/W by Node',
      'avg by (hostname) (sum by (hostname, gpu) (rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024)',
      '{{ hostname }}',
      'Bps',
      {w:8, h:8, x:16, y:64}
    ),
    timeseriesPanel(
      'ROCEv2 Combined B/W by Node',
      'avg by (hostname) ((rate(node_infiniband_port_data_received_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(node_infiniband_port_data_transmitted_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])))',
      '{{ hostname }}',
      'Bps',
      {w:8, h:10, x:0, y:72},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'}
    ),
    timeseriesPanel(
      'ROCEv2 TX B/W by Node',
      'avg by (hostname) (rate(node_infiniband_port_data_transmitted_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:8, h:10, x:8, y:72},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'}
    ),
    timeseriesPanel(
      'ROCEv2 RX B/W by Node',
      'avg by (hostname) (rate(node_infiniband_port_data_received_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:8, h:10, x:16, y:72},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'}
    ),
])