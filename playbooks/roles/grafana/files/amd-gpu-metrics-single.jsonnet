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
      {w:6, h:4, x:0, y:0}
    ),
    tempGuagePanel(
      'Max GPU Temp',
      'ceil(max by (hostname) (amd_gpu_junction_temperature{hostname=~"$hostname", oci_name=~"$oci_name"}))',
      {w:6, h:4, x:6, y:0}
    ),
    tempGuagePanel(
      'Max Mem Temp',
      'ceil(max by (hostname) (amd_gpu_memory_temperature{hostname=~"$hostname", oci_name=~"$oci_name"}))',
      {w:6, h:4, x:12, y:0}
    ),
    utilGaugePanel(
      'Avg GPU Util',
      'avg by (hostname) (amd_gpu_gfx_activity{hostname=~"$hostname", oci_name=~"$oci_name"})',
      {w:6, h:4, x:18, y:0}
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
      'amd_gpu_memory_temperature{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'celsius',
      {w:8, h:8, x:0, y:12}
    ),
    timeseriesPanel(
      'Package Powerdraw',
      'amd_gpu_package_power{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'watts',
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
      'System Clock',
      'amd_gpu_clock{clock_type="GPU_CLOCK_TYPE_SYSTEM", hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'rotkhz',
      {w:8, h:8, x:0, y:20}
    ),
    timeseriesPanel(
      'Memory Clock',
      'amd_gpu_clock{clock_type="GPU_CLOCK_TYPE_MEMORY", hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'rotkhz',
      {w:8, h:8, x:8, y:20}
    ),
    timeseriesPanel(
      'Fabric Clock',
      'amd_gpu_clock{clock_type="GPU_CLOCK_TYPE_FABRIC", hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'rotkhz',
      {w:8, h:8, x:16, y:20}
    ),
    timeseriesPanel(
      'SM Active',
      'amd_gpu_prof_sm_active{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'percentunit',
      {w:8, h:8, x:0, y:28}
    ),
    timeseriesPanel(
      'SM Occupancy',
      'amd_gpu_prof_occupancy_percent{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'percentunit',
      {w:8, h:8, x:8, y:28}
    ),
    timeseriesPanel(
      'Tensor Active',
      'amd_gpu_prof_tensor_active_percent{hostname=~"$hostname", oci_name=~"$oci_name"}',
      '{{ gpu_id }}',
      'percentunit',
      {w:8, h:8, x:16, y:28}
    ),
    timeseriesPanel(
      'FP16 Ops Rate',
      'rate(amd_gpu_prof_total_16_ops{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{ gpu_id }}',
      'ops',
      {w:8, h:8, x:0, y:36}
    ),
    timeseriesPanel(
      'FP32 Ops Rate',
      'rate(amd_gpu_prof_total_32_ops{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{ gpu_id }}',
      'ops',
      {w:8, h:8, x:8, y:36}
    ),
    timeseriesPanel(
      'FP64 Ops Rate',
      'rate(amd_gpu_prof_total_64_ops{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{ gpu_id }}',
      'ops',
      {w:8, h:8, x:16, y:36}
    ),
    timeseriesPanel(
      'XGMI Rx + Tx Combined B/W',
      'sum by (hostname, gpu_id) (rate(amd_gpu_xgmi_link_tx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]) + rate(amd_gpu_xgmi_link_rx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ gpu_id }}',
      'Bps',
      {w:8, h:8, x:0, y:44}
    ),
    timeseriesPanel(
      'XGMI Tx B/W',
      'sum by (hostname, gpu_id) (rate(amd_gpu_xgmi_link_tx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ gpu_id }}',
      'Bps',
      {w:8, h:8, x:8, y:44}
    ),
    timeseriesPanel(
      'XGMI Rx B/W',
      'sum by (hostname, gpu_id) (rate(amd_gpu_xgmi_link_rx{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{ gpu_id }}',
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
