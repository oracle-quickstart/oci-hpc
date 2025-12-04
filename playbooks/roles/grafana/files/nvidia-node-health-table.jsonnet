local g = import './g.libsonnet';
local variables = import './variables.libsonnet';

// Define all health check metrics from recording_rules.yml
local healthChecks = [
  { metric: 'node_disk_free_ok', title: 'Disk Free', columnName: 'Disk Free' },
  { metric: 'node_memory_availability_ok', title: 'Memory Available', columnName: 'Memory' },
  { metric: 'node_gpu_power_violation_ok', title: 'GPU Power', columnName: 'GPU Power' },
  { metric: 'node_gpu_board_limit_violation_ok', title: 'GPU Board Limit', columnName: 'Board Limit' },
  { metric: 'node_gpu_thermal_violation_ok', title: 'GPU Thermal', columnName: 'GPU Thermal' },
  { metric: 'node_gpu_sync_boost_violation_ok', title: 'GPU Sync Boost', columnName: 'Sync Boost' },
  { metric: 'node_gpu_reliability_violation_ok', title: 'GPU Reliability', columnName: 'GPU Reliability' },
  { metric: 'node_pcie_aer_correctable_errors_ok', title: 'PCIe Correctable', columnName: 'PCIe Corr' },
  { metric: 'node_pcie_aer_fatal_errors_ok', title: 'PCIe Fatal', columnName: 'PCIe Fatal' },
  { metric: 'node_pcie_aer_nonfatal_errors_ok', title: 'PCIe Non-Fatal', columnName: 'PCIe NonFatal' },
  { metric: 'node_pcie_bus_inaccessible_ok', title: 'PCIe Bus Access', columnName: 'PCIe Bus' },
  { metric: 'node_pcie_bus_linkwidth_ok', title: 'PCIe Link Width', columnName: 'PCIe Width' },
  { metric: 'node_rttcc_ok', title: 'RTTCC', columnName: 'RTTCC' },
  { metric: 'node_oca_ver_ok', title: 'OCA Version', columnName: 'OCA Ver' },
  { metric: 'node_rdma_device_status_ok', title: 'RDMA Device', columnName: 'RDMA Dev' },
  { metric: 'node_check_bus_issue_count_ok', title: 'Bus Issues', columnName: 'Bus Issues' },
  { metric: 'node_rdma_link_flapping_ok', title: 'RDMA Link', columnName: 'RDMA Link' },
  { metric: 'node_ecc_error_check_ok', title: 'ECC Errors', columnName: 'ECC' },
  { metric: 'node_gpu_count_ok', title: 'GPU Count', columnName: 'GPU Count' },
  { metric: 'node_gpu_row_remap_error_check', title: 'GPU Row Remap', columnName: 'Row Remap' },
  { metric: 'node_xid_error_check', title: 'XID Errors', columnName: 'XID' },
  { metric: 'node_health_status', title: 'Overall Health', columnName: 'Health' },
];

g.dashboard.new('Node Health Check Matrix')
+ g.dashboard.withUid('node-health-table')
+ g.dashboard.withDescription(|||
  Comprehensive health check status matrix for all cluster nodes.
  Shows ✓ for passing checks and ✗ for failing checks.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withRefresh('30s')
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster,
  variables.hostname,
])
+ g.dashboard.withPanels(
  g.util.grid.makeGrid([
    g.panel.table.new('Node Health Status Matrix')
    + g.panel.table.queryOptions.withTargets(
      [
        g.query.prometheus.new(
          '$PROMETHEUS_DS',
          check.metric + '{cluster_name=~"$cluster_name", hostname=~"$hostname"}',
        )
        + g.query.prometheus.withInstant(true)
        + g.query.prometheus.withFormat('table')
        + g.query.prometheus.withRefId(std.asciiUpper(std.substr(check.metric, 0, 1)))
        for check in healthChecks
      ]
    )
    + g.panel.table.queryOptions.withTransformations([
      {
        id: 'merge',
        options: {},
      },
      {
        id: 'organize',
        options: {
          excludeByName: {
            Time: true,
            __name__: true,
            instance: true,
            job: true,
          },
          indexByName: {
            hostname: 0,
            cluster_name: 1,
          },
          renameByName: {
            hostname: 'Node',
            cluster_name: 'Cluster',
            [check.metric]: check.columnName
            for check in healthChecks
          },
        },
      },
    ])
    + g.panel.table.standardOptions.withOverrides([
      // Override for all health check columns (except Node and Cluster)
      {
        matcher: {
          id: 'byRegexp',
          options: '^(?!Node|Cluster).*',
        },
        properties: [
          {
            id: 'custom.cellOptions',
            value: {
              type: 'color-text',
            },
          },
          {
            id: 'mappings',
            value: [
              {
                type: 'value',
                options: {
                  '0': {
                    text: '✗',
                    color: 'red',
                    index: 0,
                  },
                  '1': {
                    text: '✓',
                    color: 'green',
                    index: 1,
                  },
                },
              },
              {
                type: 'special',
                options: {
                  match: 'null',
                  result: {
                    text: 'N/A',
                    color: 'gray',
                    index: 2,
                  },
                },
              },
            ],
          },
          {
            id: 'custom.width',
            value: 80,
          },
          {
            id: 'custom.align',
            value: 'center',
          },
        ],
      },
      // Special override for Overall Health column
      {
        matcher: {
          id: 'byName',
          options: 'Health',
        },
        properties: [
          {
            id: 'custom.width',
            value: 100,
          },
          {
            id: 'custom.cellOptions',
            value: {
              type: 'color-background',
            },
          },
        ],
      },
      // Node column formatting
      {
        matcher: {
          id: 'byName',
          options: 'Node',
        },
        properties: [
          {
            id: 'custom.width',
            value: 200,
          },
        ],
      },
      // Cluster column formatting
      {
        matcher: {
          id: 'byName',
          options: 'Cluster',
        },
        properties: [
          {
            id: 'custom.width',
            value: 150,
          },
        ],
      },
    ])
    + g.panel.table.options.withShowHeader(true)
    + g.panel.table.options.footer.withEnablePagination(true)
    + g.panel.table.gridPos.withW(24)
    + g.panel.table.gridPos.withH(16),
  ])
)
