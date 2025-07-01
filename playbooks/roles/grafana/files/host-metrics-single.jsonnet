local g = import './g.libsonnet';
local variables = import './host-metrics-single-variables.libsonnet';
local guagePanel = import './gauge-panel.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('Host Metrics')
+ g.dashboard.withUid('host-metrics-single')
+ g.dashboard.withDescription(|||
  Host Metrics Dashboard for a single cluster node.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
  variables.oci_name,
  variables.fstype,
  variables.interface,
  variables.device,
  variables.mountpoint
])

+ g.dashboard.withPanels([
    guagePanel(
      'CPU Avail',
      'ceil(100 * (avg by (hostname, oci_name) (irate(node_cpu_seconds_total{hostname=~"$hostname",oci_name=~"$oci_name",mode="idle"}[5m]))))',
      {w:4, h:4, x:0, y:0},
      [
        g.panel.gauge.thresholdStep.withColor('red') + g.panel.gauge.thresholdStep.withValue(0),
        g.panel.gauge.thresholdStep.withColor('yellow') + g.panel.gauge.thresholdStep.withValue(10),
        g.panel.gauge.thresholdStep.withColor('green') + g.panel.gauge.thresholdStep.withValue(20),
      ]
    ),
    guagePanel(
      'Memory Avail',
      'ceil((node_memory_MemAvailable_bytes{hostname=~"$hostname",oci_name=~"$oci_name"}/node_memory_MemTotal_bytes{hostname=~"$hostname",oci_name=~"$oci_name"})*100)',
      {w:4, h:4, x:4, y:0},
      [
        g.panel.gauge.thresholdStep.withColor('red') + g.panel.gauge.thresholdStep.withValue(0),
        g.panel.gauge.thresholdStep.withColor('yellow') + g.panel.gauge.thresholdStep.withValue(10),
        g.panel.gauge.thresholdStep.withColor('green') + g.panel.gauge.thresholdStep.withValue(20),
      ]
    ),
    guagePanel(
      'Boot Vol Avail',
      'ceil((node_filesystem_avail_bytes{hostname=~"$hostname",oci_name=~"$oci_name",mountpoint=~"/",device=~"/dev/sd.*"} / node_filesystem_size_bytes{hostname=~"$hostname",oci_name=~"$oci_name",mountpoint=~"/",device=~"/dev/sda1"})*100)',
      {w:4, h:4, x:8, y:0},
      [
        g.panel.gauge.thresholdStep.withColor('red') + g.panel.gauge.thresholdStep.withValue(0),
        g.panel.gauge.thresholdStep.withColor('yellow') + g.panel.gauge.thresholdStep.withValue(10),
        g.panel.gauge.thresholdStep.withColor('green') + g.panel.gauge.thresholdStep.withValue(20),
      ]
    ),
    guagePanel(
      'CPU Pressure',
      'ceil(avg by (hostname, oci_name) (rate(node_pressure_cpu_waiting_seconds_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m]) * 100))',
      {w:4, h:4, x:12, y:0}
    ),
    guagePanel(
      'Memory Stalled',
      'ceil(avg by (hostname, oci_name) (rate(node_pressure_memory_stalled_seconds_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m]) * 100))',
      {w:4, h:4, x:16, y:0}
    ),    
    guagePanel(
      'IO Stalled',
      'ceil(avg by (hostname, oci_name) (rate(node_pressure_io_stalled_seconds_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m]) * 100))',
      {w:4, h:4, x:20, y:0}
    ),
    timeseriesPanel(
      'CPU Utilization',
      'ceil(avg by (mode) (rate(node_cpu_seconds_total{hostname=~"$hostname", mode!~"idle"}[5m])) * 100)',
      '{{ hostname }}',
      'percent',
      {w:12, h:8, x:0, y:4}
    ),
    timeseriesPanel(
      'Memory Utilization',
      'ceil((1 - (node_memory_MemAvailable_bytes{hostname=~"$hostname",oci_name=~"$oci_name"}/node_memory_MemTotal_bytes{hostname=~"$hostname",oci_name=~"$oci_name"}))*100)',
      '{{ hostname }}',
      'percent',
      {w:12, h:8, x:12, y:4}
    ),
    timeseriesPanel(
      'Disk reads',
      'irate(node_disk_read_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m])',
      '{{ device }}',
      'Bps',
      {w:12, h:8, x:0, y:12}
    ),
    timeseriesPanel(
      'Disk writes',
      'irate(node_disk_written_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m])',
      '{{ device }}',
      'Bps',
      {w:12, h:8, x:12, y:12}
    ),
    timeseriesPanel(
      'Network Traffic Received',
      'rate(node_network_receive_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device=~"$device",device!~"lo|docker.*|rdma.*"}[5m])',
      '{{ device }}',
      'Bps',
      {w:12, h:8, x:0, y:24}
    ),
    timeseriesPanel(
      'Network Traffic Transmitted',
      'rate(node_network_transmit_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device=~"$device",device!~"lo|docker.*|rdma.*"}[5m])',
      '{{ device }}',
      'Bps',
      {w:12, h:8, x:12, y:24}
    ),
])
