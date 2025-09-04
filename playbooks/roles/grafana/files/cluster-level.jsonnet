local g = import './g.libsonnet';
local variables = import './cluster-level-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';
local statPanel = import './stat-panel-single.libsonnet';
local gaugePanel = import './gauge-panel.libsonnet';

g.dashboard.new('Cluster Level Metrics')
+ g.dashboard.withUid('cluster-level-metrics')
+ g.dashboard.withDescription(|||
  Cluster Level Aggregated Metrics Dashboard
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster_name,
])
+ g.dashboard.withPanels([
 /*   statPanel(
      'Total Nodes',
      'count(count by (nodename) (node_uname_info))',
      {w:4, h:4, x:0, y:0}
    ),
    statPanel(
      'Healthy Nodes',
      'count by (cluster_name) (node_health_status{cluster_name=~"$cluster_name"} == 1)',
      {w:4, h:4, x:4, y:0}
    ),
    statPanel(
      'Total GPUs',
      'sum(max by (instance) (DCGM_FI_DEV_COUNT))',
      {w:4, h:4, x:8, y:0}
    ),    
    statPanel(
      'Healthy GPUs',
      'sum by (cluster_name) (available_gpu_count{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:8, y:0}
    ),
  */
    gaugePanel(
      'Avg CPU Util %',
      'avg by (cluster_name) (100 * (1 - avg by (hostname) (irate(node_cpu_seconds_total{cluster_name=~"$cluster_name",mode="idle"}[5m]))))',
      {w:4, h:4, x:0, y:0}
    ),
    gaugePanel(
      'Avg GPU Util %',
      'avg by (cluster_name) (DCGM_FI_DEV_GPU_UTIL{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:4, y:0}
    ),
    gaugePanel(
      'Avg Memory Usage %',
      'avg by (cluster_name) ((1 - (node_memory_MemAvailable_bytes{cluster_name=~"$cluster_name"}/node_memory_MemTotal_bytes{cluster_name=~"$cluster_name"})) * 100)',
      {w:4, h:4, x:8, y:0}
    ),
   /* 
    statPanel(
      'Max GPU Temp C',
      'max by (cluster_name) (DCGM_FI_DEV_GPU_TEMP{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:0, y:4}
    ),
    statPanel(
      'Total GPU Power W',
      'sum by (cluster_name) (DCGM_FI_DEV_POWER_USAGE{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:4, y:4}
    ),
    statPanel(
      'GPU Errors',
      'sum by (cluster_name) (DCGM_FI_DEV_XID_ERRORS{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:12, y:4}
    ),
    */
    gaugePanel(
      'Avg CPU Pressure %',
      'avg by (cluster_name) (rate(node_pressure_cpu_waiting_seconds_total{cluster_name=~"$cluster_name"}[5m]) * 100)',
      {w:4, h:4, x:12, y:4}
    ),
    gaugePanel(
      'Avg Memory Pressure %',
      'avg by (cluster_name) (rate(node_pressure_memory_stalled_seconds_total{cluster_name=~"$cluster_name"}[5m]) * 100)',
      {w:4, h:4, x:16, y:4}
    ),
    gaugePanel(
      'Avg IO Pressure %',
      'avg by (cluster_name) (rate(node_pressure_io_stalled_seconds_total{cluster_name=~"$cluster_name"}[5m]) * 100)',
      {w:4, h:4, x:20, y:4}
    ),
    timeseriesPanel(
      'Cluster CPU Utilization by Mode',
      'avg by (cluster_name, mode) (rate(node_cpu_seconds_total{cluster_name=~"$cluster_name", mode!~"idle"}[5m])) * 100',
      '{{ mode }}',
      'percent',
      {w:8, h:8, x:0, y:8}
    ),
    timeseriesPanel(  
      'Cluster Memory Usage',
      'avg by (cluster_name) ((1 - (node_memory_MemAvailable_bytes{cluster_name=~"$cluster_name"}/node_memory_MemTotal_bytes{cluster_name=~"$cluster_name"})) * 100)',
      '{{ cluster_name }}',
      'percent',
      {w:8, h:8, x:8, y:8}
    ),
    timeseriesPanel(
      'Cluster GPU Utilization',
      'avg by (cluster_name) (DCGM_FI_DEV_GPU_UTIL{cluster_name=~"$cluster_name"})',
      '{{ cluster_name }}',
      'percent',
      {w:8, h:8, x:16, y:8}
    ),
    timeseriesPanel(
      'Cluster GPU Temperature',
      'max by (cluster_name) (DCGM_FI_DEV_GPU_TEMP{cluster_name=~"$cluster_name"})',
      '{{ cluster_name }}',
      'celsius',
      {w:8, h:8, x:0, y:16}
    ),
    timeseriesPanel(
      'Cluster GPU Power Usage',
      'sum by (cluster_name) (DCGM_FI_DEV_POWER_USAGE{cluster_name=~"$cluster_name"})',
      '{{ cluster_name }}',
      'watts',
      {w:8, h:8, x:8, y:16}
    ),
    timeseriesPanel(
      'Network Traffic Total RX',
      'sum by (cluster_name) (rate(node_network_receive_bytes_total{cluster_name=~"$cluster_name",device!~"lo|docker.*|rdma.*"}[5m]))',
      '{{ cluster_name }}',
      'Bps',
      {w:8, h:8, x:16, y:16}
    ),
    timeseriesPanel(
      'Network Traffic Total TX',
      'sum by (cluster_name) (rate(node_network_transmit_bytes_total{cluster_name=~"$cluster_name",device!~"lo|docker.*|rdma.*"}[5m]))',
      '{{ cluster_name }}',
      'Bps',
      {w:8, h:8, x:0, y:24}
    ),
    timeseriesPanel(
      'Disk Read Total',
      'sum by (cluster_name) (irate(node_disk_read_bytes_total{cluster_name=~"$cluster_name"}[5m]))',
      '{{ cluster_name }}',
      'Bps',
      {w:8, h:8, x:8, y:24}
    ),
    timeseriesPanel(
      'Disk Write Total',
      'sum by (cluster_name) (irate(node_disk_written_bytes_total{cluster_name=~"$cluster_name"}[5m]))',
      '{{ cluster_name }}',
      'Bps',
      {w:8, h:8, x:16, y:24}
    ),
])