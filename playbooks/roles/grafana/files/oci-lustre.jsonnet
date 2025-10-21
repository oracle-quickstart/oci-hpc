local g = import './g.libsonnet';
local variables = import './oci-lustre-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('Lustre File System')
+ g.dashboard.withUid('oci-lustre')
+ g.dashboard.withDescription(|||
  Lustre File System
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
      'Read Throughput',
      'rate(oci_lustrefilesystem:read_throughput_count[5m])',
      '{{display_name}}:{{performance_tier}}',
      'Bps',
      {w:12, h:8, x:0, y:0}
    ),    
    timeseriesPanel(
      'Write Throughput',
      'rate(oci_lustrefilesystem:write_throughput_count[5m])',
      '{{display_name}}:{{performance_tier}}',
      'Bps',
      {w:12, h:8, x:12, y:0}
    ),    
    timeseriesPanel(
      'Data Read Operations',
      'rate(oci_lustrefilesystem:data_read_operations_count[5m])',
      '{{display_name}}:{{performance_tier}}',
      'ops',
      {w:12, h:8, x:0, y:8}
    ),    
    timeseriesPanel(
      'Data Write Operations',
      'rate(oci_lustrefilesystem:data_write_operations_count[5m])',
      '{{display_name}}:{{performance_tier}}',
      'ops',
      {w:12, h:8, x:12, y:8}
    ),    
    timeseriesPanel(
      'Capacity Util - Space',
      '100 * sum by (cluster_name, ad) (oci_lustrefilesystem:file_system_capacity_count{capacity_type="available"}) / sum by (cluster_name, ad) (oci_lustrefilesystem:file_system_capacity_count{capacity_type="total"})',
      '{{ad}}',
      'percent',
      {w:12, h:8, x:0, y:16}
    ),    
    timeseriesPanel(
      'Capacity Util - Inode',
      '100 * sum by (cluster_name, ad) (oci_lustrefilesystem:file_system_inode_capacity_count{capacity_type="available"}) / sum by (cluster_name, ad) (oci_lustrefilesystem:file_system_inode_capacity_count{capacity_type="total"})',
      '{{ad}}',
      'percent',
      {w:12, h:8, x:12, y:16}
    ),    
])

