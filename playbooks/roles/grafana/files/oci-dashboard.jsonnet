local g = import './g.libsonnet';
local variables = import './oci-variables.libsonnet';
local row = g.panel.row;

local oci_fs_metrics = [
  { expr: 'oci_FileSystemReadRequestsBySize{size="0B_to_8KiB"}', legend_format: '{{file_system}}', title: 'File system read requests by size upto 8 KiB', unit: 'none' },
  { expr: 'oci_FileSystemReadRequestsBySize{size="8KiB_to_64KiB"}', legend_format: '{{file_system}}', title: 'File system read requests by size between 8 KiB and 64KiB', unit: 'none' },
  { expr: 'oci_FileSystemReadRequestsBySize{size="64KiB_to_1MiB"}', legend_format: '{{file_system}}', title: 'File system read requests by size between 64 KiB and 1 MiB', unit: 'none' },
  { expr: 'oci_FileSystemWriteRequestsbySize{size="0B_to_8KiB"}', legend_format: '{{file_system}}', title: 'File system write requests by size upto 8 KiB', unit: 'none' },
  { expr: 'oci_FileSystemWriteRequestsbySize{size="8KiB_to_64KiB"}', legend_format: '{{file_system}}', title: 'File system write requests by size between 8 KiB and 64KiB', unit: 'none' },
  { expr: 'oci_FileSystemWriteRequestsbySize{size="64KiB_to_1MiB"}', legend_format: '{{file_system}}', title: 'File system write requests by size between 64 KiB and 1 MiB', unit: 'none' },
  { expr: 'oci_FileSystemReadThroughput', legend_format: '{{file_system}}', title: 'File system read throughput', unit: 'MiBs' },
  { expr: 'oci_FileSystemWriteThroughput', legend_format: '{{file_system}}', title: 'File system write throughput', unit: 'MiBs' },
];

local oci_mt_metrics = [
  { expr: 'oci_MountTargetHealth', legend_format: '{{mount_target}}', title: 'Mount Target Health', unit: 'percent' },
  { expr: 'oci_MountTargetConnections', legend_format: '{{mount_target}}', title: 'Mount Target Connections', unit: 'none' },
  { expr: 'oci_MountTargetIOPS', legend_format: '{{mount_target}}', title: 'Mount Target IOPS', unit: 'iops' },
  { expr: 'oci_MetadataIOPS', legend_format: '{{mount_target}}', title: 'Metadata IOPS', unit: 'iops' },
  { expr: 'oci_MountTargetReadThroughput', legend_format: '{{mount_target}}', title: 'Mount Target Read Throughput', unit: 'MiBs' },
  { expr: 'oci_MountTargetWriteThroughput', legend_format: '{{mount_target}}', title: 'Mount Target Write Throughput', unit: 'MiBs' },
];

local oci_lustre_metrics = [
  { expr: 'oci_FileSystemCapacity{capacity_type=~"total"}', legend_format: '{{resource_name}}', title: 'Provisioned File System Capacity (Total)', unit: 'bytes' },
  { expr: 'oci_FileSystemCapacity{capacity_type=~"available"}', legend_format: '{{resource_name}}', title: 'Provisioned File System Capacity (Available)', unit: 'bytes' },
  { expr: 'oci_TotalSize', legend_format: '{{file_system}}', title: 'Actual File System Capacity (Total)', unit: 'bytes' },
  { expr: 'oci_AvailableSize', legend_format: '{{file_system}}', title: 'Actual File System Capacity (Available)', unit: 'bytes' },
  { expr: 'oci_FileSystemInodeCapacity{capacity_type=~"total"}', legend_format: '{{resource_name}}', title: 'File System Inode Capacity (Total)', unit: 'none' },
  { expr: 'oci_FileSystemInodeCapacity{capacity_type=~"available"}', legend_format: '{{resource_name}}', title: 'File System Inode Capacity (Available)', unit: 'none' },
  { expr: 'oci_ReadThroughput', legend_format: '{{client_name}}', title: 'Read Throughput (Real-time)', unit: 'MiBs' },
  { expr: 'oci_WriteThroughput', legend_format: '{{client_name}}', title: 'Write Throughput (Real-time)', unit: 'MiBs' },
  { expr: 'oci_DataReadOperations', legend_format: '{{file_system}}', title: 'Data Read Operations (Real-time)', unit: 'none' },
  { expr: 'oci_DataWriteOperations', legend_format: '{{file_system}}', title: 'Data Write Operations (Real-time)', unit: 'none' },
  { expr: 'sum(oci_MetaDataOperations{operation_type=~".+"}[5m])', legend_format: '{{resource_name}}', title: 'Metadata Operations (5 min Rate)', unit: 'ops' },
];

g.dashboard.new('OCI File Storage Service Dashboard')
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.mount_target,
  variables.file_system,
  variables.fss_ad
])
+ g.dashboard.withPanels(
  g.util.grid.makeGrid([
    row.new('FSS File Systems')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format)
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in oci_fs_metrics
      ]),
    row.new('Mount Targets')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format)
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in oci_mt_metrics
      ]),
    row.new('Lustre File Systems')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format)
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in oci_lustre_metrics
    ])
  ])
)