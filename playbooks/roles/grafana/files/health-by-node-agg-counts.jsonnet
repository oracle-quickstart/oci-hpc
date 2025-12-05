local g = import './g.libsonnet';
local variables = import './node-health-table-variables.libsonnet';

// Define all health check metrics from recording_rules.yml
local healthChecks = [
  { metric: 'node_disk_free_ok', title: 'Disk Free' },
  { metric: 'node_memory_availability_ok', title: 'Memory' },
  { metric: 'node_gpu_power_violation_ok', title: 'GPU Power' },
  { metric: 'node_gpu_board_limit_violation_ok', title: 'Board Limit' },
  { metric: 'node_gpu_thermal_violation_ok', title: 'GPU Thermal' },
  { metric: 'node_gpu_sync_boost_violation_ok', title: 'Sync Boost' },
  { metric: 'node_gpu_reliability_violation_ok', title: 'GPU Reliability' },
  { metric: 'node_pcie_aer_correctable_errors_ok', title: 'PCIe Corr' },
  { metric: 'node_pcie_aer_fatal_errors_ok', title: 'PCIe Fatal' },
  { metric: 'node_pcie_aer_nonfatal_errors_ok', title: 'PCIe NonFatal' },
  { metric: 'node_pcie_bus_inaccessible_ok', title: 'PCIe Bus' },
  { metric: 'node_pcie_bus_linkwidth_ok', title: 'PCIe Width' },
  { metric: 'node_rttcc_ok', title: 'RTTCC' },
  { metric: 'node_oca_ver_ok', title: 'OCA Ver' },
  { metric: 'node_rdma_device_status_ok', title: 'RDMA Dev' },
  { metric: 'node_check_bus_issue_count_ok', title: 'Bus Issues' },
  { metric: 'node_rdma_link_flapping_ok', title: 'RDMA Link' },
  { metric: 'node_ecc_error_check_ok', title: 'ECC' },
  { metric: 'node_gpu_count_ok', title: 'GPU Count' },
  { metric: 'node_gpu_row_remap_error_check', title: 'Row Remap' },
  { metric: 'node_xid_error_check', title: 'XID' },
  { metric: 'node_health_status', title: 'Overall Health' },
];

g.dashboard.new('Health by Node Counts')
+ g.dashboard.withUid('health-by-node-counts')
+ g.dashboard.withDescription(|||
  Health checks as rows, nodes as columns, with fail/success counts.
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
+ g.dashboard.withPanels([
    g.panel.table.new('Health Check Status Matrix with Counts')
    + g.panel.table.queryOptions.withTargets([
      // Query A: All health check data with hostname and check labels
      g.query.prometheus.new(
        '$PROMETHEUS_DS',
        |||
          (
            label_replace(node_disk_free_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "Disk Free", "", "")
            or
            label_replace(node_memory_availability_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "Memory", "", "")
            or
            label_replace(node_gpu_power_violation_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "GPU Power", "", "")
            or
            label_replace(node_gpu_board_limit_violation_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "Board Limit", "", "")
            or
            label_replace(node_gpu_thermal_violation_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "GPU Thermal", "", "")
            or
            label_replace(node_gpu_sync_boost_violation_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "Sync Boost", "", "")
            or
            label_replace(node_gpu_reliability_violation_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "GPU Reliability", "", "")
            or
            label_replace(node_pcie_aer_correctable_errors_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "PCIe Corr", "", "")
            or
            label_replace(node_pcie_aer_fatal_errors_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "PCIe Fatal", "", "")
            or
            label_replace(node_pcie_aer_nonfatal_errors_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "PCIe NonFatal", "", "")
            or
            label_replace(node_pcie_bus_inaccessible_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "PCIe Bus", "", "")
            or
            label_replace(node_pcie_bus_linkwidth_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "PCIe Width", "", "")
            or
            label_replace(node_rttcc_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "RTTCC", "", "")
            or
            label_replace(node_oca_ver_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "OCA Ver", "", "")
            or
            label_replace(node_rdma_device_status_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "RDMA Dev", "", "")
            or
            label_replace(node_check_bus_issue_count_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "Bus Issues", "", "")
            or
            label_replace(node_rdma_link_flapping_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "RDMA Link", "", "")
            or
            label_replace(node_ecc_error_check_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "ECC", "", "")
            or
            label_replace(node_gpu_count_ok{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "GPU Count", "", "")
            or
            label_replace(node_gpu_row_remap_error_check{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "Row Remap", "", "")
            or
            label_replace(node_xid_error_check{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "XID", "", "")
            or
            label_replace(node_health_status{cluster_name=~"$cluster_name", hostname=~"$hostname"}, "check", "Overall Health", "", "")
          )
        |||
      )
      + g.query.prometheus.withInstant(true)
      + g.query.prometheus.withFormat('table')
      + g.query.prometheus.withRefId('A'),
    ])
    + g.panel.table.queryOptions.withTransformations([
      // Clean up columns
      {
        id: 'organize',
        options: {
          excludeByName: {
            Time: true,
            __name__: true,
            instance: true,
            job: true,
            cluster_name: true,
          },
        },
      },
      // Group by check and hostname, calculate counts
      {
        id: 'groupBy',
        options: {
          fields: {
            check: {
              aggregations: [],
              operation: 'groupby',
            },
            Value: {
              aggregations: ['count', 'sum'],
              operation: 'aggregate',
            },
          },
        },
      },
      // Calculate failures
      {
        id: 'calculateField',
        options: {
          mode: 'binary',
          binary: {
            left: 'Value (count)',
            operator: '-',
            right: 'Value (sum)',
          },
          alias: 'Failures',
          replaceFields: false,
        },
      },
      // Rename and organize
      {
        id: 'organize',
        options: {
          excludeByName: {
            'Value (count)': true,
          },
          indexByName: {
            check: 0,
            Failures: 1,
            'Value (sum)': 2,
          },
          renameByName: {
            check: 'Health Check',
            'Value (sum)': 'Successes',
          },
        },
      },
    ])
    + g.panel.table.standardOptions.withOverrides([
      // Override for all hostname columns (not Health Check, Failures, or Successes)
      {
        matcher: {
          id: 'byRegexp',
          options: '^(?!Health Check|Failures|Successes).*',
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
            value: 100,
          },
          {
            id: 'custom.align',
            value: 'center',
          },
        ],
      },
      // Health Check column formatting
      {
        matcher: {
          id: 'byName',
          options: 'Health Check',
        },
        properties: [
          {
            id: 'custom.width',
            value: 180,
          },
        ],
      },
      // Failures column - red background
      {
        matcher: {
          id: 'byName',
          options: 'Failures',
        },
        properties: [
          {
            id: 'custom.width',
            value: 80,
          },
          {
            id: 'custom.align',
            value: 'center',
          },
          {
            id: 'custom.cellOptions',
            value: {
              type: 'color-background',
            },
          },
          {
            id: 'thresholds',
            value: {
              mode: 'absolute',
              steps: [
                {
                  color: 'green',
                  value: null,
                },
                {
                  color: 'red',
                  value: 1,
                },
              ],
            },
          },
        ],
      },
      // Successes column - green background
      {
        matcher: {
          id: 'byName',
          options: 'Successes',
        },
        properties: [
          {
            id: 'custom.width',
            value: 90,
          },
          {
            id: 'custom.align',
            value: 'center',
          },
          {
            id: 'custom.cellOptions',
            value: {
              type: 'color-background',
            },
          },
          {
            id: 'thresholds',
            value: {
              mode: 'absolute',
              steps: [
                {
                  color: 'red',
                  value: null,
                },
                {
                  color: 'green',
                  value: 1,
                },
              ],
            },
          },
        ],
      },
    ])
    + g.panel.table.options.withShowHeader(true)
    + g.panel.table.options.footer.withEnablePagination(true)
    + g.panel.table.gridPos.withX(0)
    + g.panel.table.gridPos.withY(0)
    + g.panel.table.gridPos.withW(24)
    + g.panel.table.gridPos.withH(18),
])
