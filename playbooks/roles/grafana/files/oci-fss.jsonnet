local g = import './g.libsonnet';
local variables = import './oci-fss-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('File Storage Service')
+ g.dashboard.withUid('oci-fss')
+ g.dashboard.withDescription(|||
  File Storage Service
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-5m')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
  variables.oci_name,
  variables.cluster_name,
])

+ g.dashboard.withPanels([
    timeseriesPanel(
      'FileSystem Read Throughput',
      'rate(oci_filestorage:file_system_read_throughput_count[5m])',
      '{{display_name}}',
      'Bps',
      {w:12, h:8, x:0, y:0}
    ),    
    timeseriesPanel(
      'FileSystem Write Throughput',
      'rate(oci_filestorage:file_system_write_throughput_count[5m])',
      '{{display_name}}',
      'Bps',
      {w:12, h:8, x:12, y:0}
    ),    
    timeseriesPanel(
      'MountTarget Read Throughput',
      'rate(oci_filestorage:mount_target_read_throughput_count[5m])',
      '{{display_name}}:{{current_throughput}}Gbps',
      'Bps',
      {w:12, h:8, x:0, y:8}
    ),    
    timeseriesPanel(
      'MountTarget Write Throughput',
      'rate(oci_filestorage:mount_target_write_throughput_count[5m])',
      '{{display_name}}:{{current_throughput}}Gbps',
      'Bps',
      {w:12, h:8, x:12, y:8}
    ),    
    timeseriesPanel(
      'Metadata IOPS',
      'rate(oci_filestorage:metadata_iops_count[5m])',
      '{{display_name}}:{{operation}}',
      'iops',
      {w:12, h:8, x:0, y:16}
    ),    
    timeseriesPanel(
      'MountTarget Connections',
      'rate(oci_filestorage:mount_target_connections_count[5m])',
      '{{display_name}}',
      'none',
      {w:12, h:8, x:12, y:16}
    ),    
    timeseriesPanel(
      'MountTarget Health',
      'rate(oci_filestorage:mount_target_health_count[5m])',
      '{{display_name}}',
      'percent',
      {w:12, h:8, x:0, y:24}
    ),    
])

