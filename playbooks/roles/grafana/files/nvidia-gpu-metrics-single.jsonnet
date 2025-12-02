local g = import './g.libsonnet';
local variables = import './nvidia-gpu-metrics-single-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';
local statPanel = import './stat-panel-single.libsonnet';
local tempGuagePanel = import './gauge-panel.libsonnet';
local statPanelXid = import './stat-panel.libsonnet';
local utilGaugePanel = import './gauge-panel-util.libsonnet';

g.dashboard.new('NVIDIA GPU Metrics')
+ g.dashboard.withUid('nvidia-gpu-metrics-single')
+ g.dashboard.withDescription(|||
  GPU Metrics Dashboard for a single cluster node.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-5m')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
  variables.oci_name,
])
+ g.dashboard.withPanels([
    statPanel(
      'Avail GPU',
      'available_gpu_count{hostname=~"$hostname", oci_name=~"$oci_name"}',
      {w:4, h:4, x:0, y:0}
    ),
    tempGuagePanel(
      'Max Temp / Slowdown',
      'ceil(max by (Hostname) (DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"}) / max by (Hostname) (DCGM_FI_DEV_SLOWDOWN_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"}) * 100)',
      {w:4, h:4, x:4, y:0}
    ),
    tempGuagePanel(
      'Max Temp / Shutdown',
      'ceil(max by (Hostname) (DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"}) / max by (Hostname) (DCGM_FI_DEV_SHUTDOWN_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"}) * 100)',
      {w:4, h:4, x:8, y:0}
    ),
    utilGaugePanel(
      'Avg GPU Util',
      'avg by (Hostname) (DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      {w:4, h:4, x:12, y:0}
    ),
    statPanelXid(
      'Last Xid by GPU',
      'max by(Hostname, gpu) (DCGM_FI_DEV_XID_ERRORS{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      {w:8, h:4, x:16, y:0}
    ),    
    timeseriesPanel(
      'GPU Temperature',
      'DCGM_FI_DEV_GPU_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'celsius',
      {w:8, h:8, x:0, y:4}
    ),
    timeseriesPanel(
      'GPU Powerdraw',
      'DCGM_FI_DEV_POWER_USAGE{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'watts',
      {w:8, h:8, x:8, y:4}
    ),
    timeseriesPanel(
      'GPU Utilization',
      'DCGM_FI_DEV_GPU_UTIL{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percent',
      {w:8, h:8, x:16, y:4}
    ),
    timeseriesPanel(
      'GPU Memory Temperature',
      'DCGM_FI_DEV_MEMORY_TEMP{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'celsius',
      {w:8, h:8, x:0, y:12}
    ),
    timeseriesPanel(
      'SM Clock',
      'DCGM_FI_DEV_SM_CLOCK{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'rotkhz',
      {w:8, h:8, x:8, y:12}
    ),
    timeseriesPanel(
      'GPU Memory Copy Utilization',
      'DCGM_FI_DEV_MEM_COPY_UTIL{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percent',
      {w:8, h:8, x:16, y:12}
    ),
    timeseriesPanel(
      'SM Active',
      'DCGM_FI_PROF_SM_ACTIVE{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:0, y:20}
    ),
    timeseriesPanel(
      'SM Occupancy',
      'DCGM_FI_PROF_SM_OCCUPANCY{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:8, y:20}
    ),
    timeseriesPanel(
      'DRAM Active',
      'DCGM_FI_PROF_DRAM_ACTIVE{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percent',
      {w:8, h:8, x:16, y:20}
    ),
    timeseriesPanel(
      'FP16 Pipe Active',
      'DCGM_FI_PROF_PIPE_FP16_ACTIVE{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:0, y:28}
    ),
    timeseriesPanel(
      'FP32 Pipe Active',
      'DCGM_FI_PROF_PIPE_FP32_ACTIVE{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:8, y:28}
    ),
    timeseriesPanel(
      'FP64 Pipe Active',
      'DCGM_FI_PROF_PIPE_FP64_ACTIVE{Hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:16, y:28}
    ),
    timeseriesPanel(
      'NVLink Rx + Tx Combined B/W',
      'sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024 ',
      '{{ gpu }}',
      'Bps',
      {w:8, h:8, x:0, y:36}
    ),
    timeseriesPanel(
      'NVLink Tx B/W',
      'sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024',
      '{{ gpu }}',
      'Bps',
      {w:8, h:8, x:8, y:36}
    ),
    timeseriesPanel(
      'NVLink Rx B/W',
      'sum by (hostname, gpu) (rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024',
      '{{ gpu }}',
      'Bps',
      {w:8, h:8, x:16, y:36}
    ),
    timeseriesPanel(
      'ROCEv2 Rx + Tx Combined B/W',
      '(rate(node_infiniband_port_data_received_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(node_infiniband_port_data_transmitted_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ device }}',
      'Bps',
      {w:8, h:10, x:0, y:44},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'},
    ),
    timeseriesPanel(
      'ROCEv2 Tx B/W',
      'rate(node_infiniband_port_data_transmitted_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{ device }}',
      'Bps',
      {w:8, h:10, x:8, y:44},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'},
    ),
    timeseriesPanel(
      'ROCEv2 Rx B/W',
      'rate(node_infiniband_port_data_received_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{ device }}',
      'Bps',
      {w:8, h:10, x:16, y:44},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'},
    ),
])
