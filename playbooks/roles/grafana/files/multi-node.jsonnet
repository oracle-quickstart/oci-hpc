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
])
+ g.dashboard.withPanels([
    // Host Metrics Time Series
    timeseriesPanel(
      'CPU Utilization by Node',
      'ceil(avg by (hostname) (rate(node_cpu_seconds_total{hostname=~"$hostname", mode!~"idle"}[5m])) * 100)',
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
      'Network RX by Node',
      'avg by (hostname) (rate(node_network_receive_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device!~"lo|docker.*|rdma.*"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:12, h:8, x:0, y:16}
    ),
    timeseriesPanel(
      'Network TX by Node',
      'avg by (hostname) (rate(node_network_transmit_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device!~"lo|docker.*|rdma.*"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:12, h:8, x:12, y:16}
    ),
    // GPU Metrics Time Series
    timeseriesPanel(
      'GPU Temperature by Node',
      'avg by (Hostname) (DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'celsius',
      {w:8, h:8, x:0, y:24}
    ),
    timeseriesPanel(
      'GPU Power Usage by Node',
      'avg by (Hostname) (DCGM_FI_DEV_POWER_USAGE{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'watts',
      {w:8, h:8, x:8, y:24}
    ),
    timeseriesPanel(
      'GPU Utilization by Node',
      'avg by (Hostname) (DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'percent',
      {w:8, h:8, x:16, y:24}
    ),
    timeseriesPanel(
      'GPU Memory Temperature by Node',
      'avg by (Hostname) (DCGM_FI_DEV_MEMORY_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'celsius',
      {w:8, h:8, x:0, y:32}
    ),
    timeseriesPanel(
      'GPU SM Clock by Node',
      'avg by (Hostname) (DCGM_FI_DEV_SM_CLOCK{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'hertz',
      {w:8, h:8, x:8, y:32}
    ),
    timeseriesPanel(
      'GPU Memory Copy Utilization by Node',
      'avg by (Hostname) (DCGM_FI_DEV_MEM_COPY_UTIL{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      '{{ Hostname }}',
      'percent',
      {w:8, h:8, x:16, y:32}
    ),
    timeseriesPanel(
      'NVLink Combined B/W by Node',
      'avg by (hostname) (sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024)',
      '{{ hostname }}',
      'Bps',
      {w:8, h:8, x:0, y:40}
    ),
    timeseriesPanel(
      'NVLink TX B/W by Node',
      'avg by (hostname) (sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024)',
      '{{ hostname }}',
      'Bps',
      {w:8, h:8, x:8, y:40}
    ),
    timeseriesPanel(
      'NVLink RX B/W by Node',
      'avg by (hostname) (sum by (hostname, gpu) (rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024)',
      '{{ hostname }}',
      'Bps',
      {w:8, h:8, x:16, y:40}
    ),
    timeseriesPanel(
      'ROCEv2 Combined B/W by Node',
      'avg by (hostname) ((rate(node_infiniband_port_data_received_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(node_infiniband_port_data_transmitted_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])))',
      '{{ hostname }}',
      'Bps',
      {w:8, h:10, x:0, y:48},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'}
    ),
    timeseriesPanel(
      'ROCEv2 TX B/W by Node',
      'avg by (hostname) (rate(node_infiniband_port_data_transmitted_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:8, h:10, x:8, y:48},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'}
    ),
    timeseriesPanel(
      'ROCEv2 RX B/W by Node',
      'avg by (hostname) (rate(node_infiniband_port_data_received_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ hostname }}',
      'Bps',
      {w:8, h:10, x:16, y:48},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'}
    ),
])