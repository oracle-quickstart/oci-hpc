local g = import './g.libsonnet';
local variables = import './storage-metrics-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('Storage Metrics')
+ g.dashboard.withUid('storage-metrics-single')
+ g.dashboard.withDescription(|||
  Storage Metrics Dashboard for a single cluster node.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
  variables.oci_name,
  variables.fstype,
  variables.mountpoint,
  variables.fss_mount,
  variables.export
])

+ g.dashboard.withPanels([
    timeseriesPanel(
      'Read Throughput',
      'rate(node_mountstats_nfs_total_read_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{hostname}}:{{export}}',
      'Bps',
      {w:12, h:8, x:0, y:0}
    ),
    timeseriesPanel(
      'Write Throughput',
      'rate(node_mountstats_nfs_total_write_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{hostname}}:{{export}}',
      'Bps',
      {w:12, h:8, x:12, y:0}
    ),
    timeseriesPanel(
      'Metadata IOPS',
      'sum by(oci_name, hostname) (rate(node_mountstats_nfs_operations_requests_total{hostname=~"$hostname", oci_name=~"$oci_name", operation!~"READ|WRITE"}[5m]))',
      '{{hostname}}',
      'iops',
      {w:12, h:8, x:0, y:8}
    ),    
    timeseriesPanel(
      'Read/Write IOPS',
      'sum by(oci_name, hostname) (rate(node_mountstats_nfs_operations_requests_total{hostname=~"$hostname", oci_name=~"$oci_name", operation=~"READ|WRITE"}[5m]))',
      '{{hostname}}',
      'iops',
      {w:12, h:8, x:12, y:8}
    ),
    timeseriesPanel(
      'NFS Request Time',
      'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_request_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{hostname}}:{{export}}',
      'cps',
      {w:12, h:8, x:0, y:16}
    ),
    timeseriesPanel(
      'NFS Response Time',
      'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_response_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{hostname}}:{{export}}',
      's',
      {w:12, h:8, x:12, y:16}
    ),
    timeseriesPanel(
      'NFS Retransmissions',
      'rate(node_nfs_rpc_retransmissions_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m])',
      '{{hostname}}:{{export}}',
      'cps',
      {w:12, h:8, x:0, y:24}
    ),
    timeseriesPanel(
      'NFS Queue Time',
      'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_queue_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[5m]))',
      '{{hostname}}:{{export}}',
      's',
      {w:12, h:8, x:12, y:24}
    ),
])

