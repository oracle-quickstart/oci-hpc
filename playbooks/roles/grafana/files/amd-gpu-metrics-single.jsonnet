local g = import './g.libsonnet';
local variables = import './amd-gpu-metrics-single-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';
local statPanel = import './stat-panel-single.libsonnet';
local tempGuagePanel = import './gauge-panel.libsonnet';
local statPanelXid = import './stat-panel.libsonnet';
local utilGaugePanel = import './gauge-panel-util.libsonnet';

g.dashboard.new('AMD GPU Metrics')
+ g.dashboard.withUid('amd-gpu-metrics-single')
+ g.dashboard.withDescription(|||
  AMD GPU Metrics Dashboard for a single cluster node.
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
      'amd_gpu_nodes_total{hostname=~"$hostname", oci_name=~"$oci_name"}',
      {w:4, h:4, x:0, y:0}
    ),
    tempGuagePanel(
      'Max GPU Temp',
      'ceil(max by (hostname) (amd_gpu_junction_temperature{Hostname=~"$hostname", oci_name=~"$oci_name"}) / 85) * 100)',
      {w:4, h:4, x:4, y:0}
    ),
    tempGuagePanel(
      'Max Temp / Shutdown',
      'ceil(max by (hostname) (amd_gpu_junction_temperature{Hostname=~"$hostname", oci_name=~"$oci_name"}) / 92) * 100)',
      {w:4, h:4, x:8, y:0}
    ),
    utilGaugePanel(
      'Avg GPU Util',
      'avg by (hostname) (amd_gpu_gfx_activity{hostname=~"$hostname", oci_name=~"$oci_name"})',
      {w:4, h:4, x:12, y:0}
    ),
    statPanelXid(
      'Last Xid by GPU',
      'max by(Hostname, gpu) (DCGM_FI_DEV_XID_ERRORS{Hostname=~"$hostname", oci_name=~"$oci_name"})',
      {w:8, h:4, x:16, y:0}
    ),    
    timeseriesPanel(
      'GPU Temperature',
      'amd_gpu_junction_temperature{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'celsius',
      {w:8, h:8, x:0, y:4}
    ),
    timeseriesPanel(
      'GPU Powerdraw',
      'amd_gpu_power_usage{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'watts',
      {w:8, h:8, x:8, y:4}
    ),
    timeseriesPanel(
      'GPU Utilization',
      'amd_gpu_gfx_activity{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
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
      'GPU Memory Utilization',
      'amd_gpu_used_vram{hostname=~"$hostname", oci_name=~"$oci_name"} / amd_gpu_total_vram{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
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
      'XGMI Rx + Tx Combined B/W',
      'sum by (hostname, gpu_id) (rate(amd_gpu_xgmi_link_tx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(amd_gpu_xgmi_link_rx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ gpu_id }}',
      'Bps',
      {w:8, h:8, x:0, y:36}
    ),
    timeseriesPanel(
      'XGMI Tx B/W',
      'sum by (hostname, gpu_id) (rate(amd_gpu_xgmi_link_tx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ gpu_id }}',
      'Bps',
      {w:8, h:8, x:8, y:36}
    ),
    timeseriesPanel(
      'XGMI Rx B/W',
      'sum by (hostname, gpu_id) (rate(amd_gpu_xgmi_link_rx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ gpu_id }}',
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
