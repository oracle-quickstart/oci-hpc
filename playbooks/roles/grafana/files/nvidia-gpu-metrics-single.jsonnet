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
      'Detected GPU',
      'gpu_available_count{hostname=~"$hostname", oci_name=~"$oci_name"}',
      {w:4, h:4, x:0, y:0}
    ),
    tempGuagePanel(
      'Max Temp / Slowdown',
      'ceil(max by (hostname) (DCGM_FI_DEV_GPU_TEMP{hostname=~"$hostname", oci_name=~"$oci_name"}) / max by (hostname) (DCGM_FI_DEV_SLOWDOWN_TEMP{hostname=~"$hostname", oci_name=~"$oci_name"}) * 100)',
      {w:4, h:4, x:4, y:0}
    ),
    tempGuagePanel(
      'Max Temp / Shutdown',
      'ceil(max by (hostname) (DCGM_FI_DEV_GPU_TEMP{hostname=~"$hostname", oci_name=~"$oci_name"}) / max by (hostname) (DCGM_FI_DEV_SHUTDOWN_TEMP{hostname=~"$hostname", oci_name=~"$oci_name"}) * 100)',
      {w:4, h:4, x:8, y:0}
    ),
    utilGaugePanel(
      'Avg GPU Util',
      'avg by (hostname) (DCGM_FI_DEV_GPU_UTIL{hostname=~"$hostname", oci_name=~"$oci_name"})',
      {w:4, h:4, x:12, y:0}
    ),
    statPanelXid(
      'Last Xid by GPU',
      'max by(hostname, gpu) (DCGM_FI_DEV_XID_ERRORS{hostname=~"$hostname", oci_name=~"$oci_name"})',
      {w:8, h:4, x:16, y:0}
    ),    
    timeseriesPanel(
      'GPU Temperature',
      'DCGM_FI_DEV_GPU_TEMP{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'celsius',
      {w:8, h:8, x:0, y:4}
    ),
    timeseriesPanel(
      'GPU Powerdraw',
      'DCGM_FI_DEV_POWER_USAGE{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'watts',
      {w:8, h:8, x:8, y:4}
    ),
    timeseriesPanel(
      'GPU Utilization',
      'DCGM_FI_DEV_GPU_UTIL{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percent',
      {w:8, h:8, x:16, y:4}
    ),
    timeseriesPanel(
      'GPU Memory Temperature',
      'DCGM_FI_DEV_MEMORY_TEMP{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'celsius',
      {w:8, h:8, x:0, y:12}
    ),
    timeseriesPanel(
      'SM Clock',
      'DCGM_FI_DEV_SM_CLOCK{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'rotkhz',
      {w:8, h:8, x:8, y:12}
    ),
    timeseriesPanel(
      'GPU Memory Copy Utilization',
      'DCGM_FI_DEV_MEM_COPY_UTIL{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percent',
      {w:8, h:8, x:16, y:12}
    ),
    timeseriesPanel(
      'SM Active',
      'DCGM_FI_PROF_SM_ACTIVE{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:0, y:20}
    ),
    timeseriesPanel(
      'SM Occupancy',
      'DCGM_FI_PROF_SM_OCCUPANCY{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:8, y:20}
    ),
    timeseriesPanel(
      'DRAM Active',
      'DCGM_FI_PROF_DRAM_ACTIVE{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percent',
      {w:8, h:8, x:16, y:20}
    ),
    timeseriesPanel(
      'FP16 Pipe Active',
      'DCGM_FI_PROF_PIPE_FP16_ACTIVE{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:0, y:28}
    ),
    timeseriesPanel(
      'FP32 Pipe Active',
      'DCGM_FI_PROF_PIPE_FP32_ACTIVE{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:8, y:28}
    ),
    timeseriesPanel(
      'FP64 Pipe Active',
      'DCGM_FI_PROF_PIPE_FP64_ACTIVE{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:8, h:8, x:16, y:28}
    ),
    timeseriesPanel(
      'Pipe Tensor Active',
      'DCGM_FI_PROF_PIPE_TENSOR_ACTIVE{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu }} {{GPU_I_PROFILE}}',
      'percentunit',
      {w:24, h:8, x:0, y:36}
    ),
    timeseriesPanel(
      'NVLink Rx + Tx Combined B/W',
      'sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024 ',
      '{{ gpu }}',
      'Bps',
      {w:8, h:8, x:0, y:44}
    ),
    timeseriesPanel(
      'NVLink Tx B/W',
      'sum by (hostname, gpu) (rate(nvlink_raw_tx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024',
      '{{ gpu }}',
      'Bps',
      {w:8, h:8, x:8, y:44}
    ),
    timeseriesPanel(
      'NVLink Rx B/W',
      'sum by (hostname, gpu) (rate(nvlink_raw_rx_kib_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])) * 1024',
      '{{ gpu }}',
      'Bps',
      {w:8, h:8, x:16, y:44}
    ),
    timeseriesPanel(
      'ROCEv2 Rx + Tx Combined B/W',
      '(rate(ib_port_rcv_data{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(ib_port_xmit_data{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ interface }}',
      'Bps',
      {w:8, h:10, x:0, y:52},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'},
    ),
    timeseriesPanel(
      'ROCEv2 Tx B/W',
      'rate(ib_port_xmit_data{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{ interface }}',
      'Bps',
      {w:8, h:10, x:8, y:52},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'},
    ),
    timeseriesPanel(
      'ROCEv2 Rx B/W',
      'rate(ib_port_rcv_data{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{ interface }}',
      'Bps',
      {w:8, h:10, x:16, y:52},
      {calcs: ['delta'], displayMode: 'table', placement: 'right'},
    ),    
])
