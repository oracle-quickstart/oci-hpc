local g = import './g.libsonnet';
local variables = import './command-center-variables.libsonnet';
local statPanel = import './stat-panel-single.libsonnet';

// Query for max throttling across all types per node
local maxThrottleQuery = 'max by (hostname, cluster_name, vendor) (node_gpu_power_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_gpu_board_limit_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_gpu_sync_boost_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_gpu_reliability_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_amd_gpu_power_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_amd_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_amd_gpu_hbm_thermal_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_amd_gpu_processor_hot_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_amd_gpu_vr_thermal_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"} or node_amd_gpu_current_violation_percentage{cluster_name=~"$cluster_name", hostname!~".*controller.*|.*login*|.*backup*"})';

// Throttling thresholds
local throttleThresholds = [
  { color: 'green', value: null },
  { color: 'yellow', value: 5 },
  { color: 'orange', value: 15 },
  { color: 'red', value: 30 },
];

g.dashboard.new('GPU Throttling Overview')
+ g.dashboard.withUid('gpu-throttling-overview')
+ g.dashboard.withDescription('Cluster-wide GPU Throttling Status Overview')
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-1h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster,
])
+ g.dashboard.withPanels([
    // Summary stats row
    statPanel(
      'Nodes Throttling',
      'sum(max by (hostname) (node_gpu_power_violation_percentage{cluster_name=~"$cluster_name"} or node_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_power_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"}) > bool 5) or vector(0)',
      {w: 4, h: 4, x: 0, y: 0}
    ),
    statPanel(
      'Avg Power Throttle %',
      'avg(node_gpu_power_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_power_violation_percentage{cluster_name=~"$cluster_name"})',
      {w: 4, h: 4, x: 4, y: 0}
    ),
    statPanel(
      'Avg Thermal Throttle %',
      'avg(node_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"})',
      {w: 4, h: 4, x: 8, y: 0}
    ),
    statPanel(
      'Max Power Throttle %',
      'max(node_gpu_power_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_power_violation_percentage{cluster_name=~"$cluster_name"})',
      {w: 4, h: 4, x: 12, y: 0}
    ),
    statPanel(
      'Max Thermal Throttle %',
      'max(node_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"})',
      {w: 4, h: 4, x: 16, y: 0}
    ),
    statPanel(
      'Total Compute Nodes',
      'count(node_health_status{hostname!~".*controller*|.*login*|.*backup*",cluster_name=~"$cluster_name"})',
      {w: 4, h: 4, x: 20, y: 0}
    ),

    // Compute Throttling Status - shows max throttling % per node
    g.panel.stat.new('Compute Throttling Status')
        + g.panel.stat.queryOptions.withTargets([
            g.query.prometheus.new('$PROMETHEUS_DS', maxThrottleQuery)
            + g.query.prometheus.withLegendFormat('{{hostname}}')
        ])
        + g.panel.stat.standardOptions.withUnit('percent')
        + g.panel.stat.standardOptions.withDecimals(0)
        + g.panel.stat.options.withTextMode('name')
        + g.panel.stat.options.withColorMode('background')
        + g.panel.stat.options.withGraphMode('none')
        + g.panel.stat.standardOptions.thresholds.withMode('absolute')
        + g.panel.stat.standardOptions.thresholds.withSteps(throttleThresholds)
        + g.panel.stat.gridPos.withW(24)
        + g.panel.stat.gridPos.withH(5)
        + g.panel.stat.gridPos.withX(0)
        + g.panel.stat.gridPos.withY(4)
        + g.panel.stat.standardOptions.withLinks([
            {
              title: 'GPU Throttling Details',
              url: '/d/${__field.labels.vendor}-gpu-throttling/gpu-throttling?var-hostname=${__field.labels.hostname}',
              targetBlank: true,
            }
        ]),

    // Historical throttling state timeline
    g.panel.stateTimeline.new('Historical Throttling Status')
      + g.panel.stateTimeline.queryOptions.withTargets([
          g.query.prometheus.new('$PROMETHEUS_DS', maxThrottleQuery)
          + g.query.prometheus.withLegendFormat('{{hostname}}')
      ])
      + g.panel.stateTimeline.options.withShowValue('never')
      + g.panel.stateTimeline.options.withPerPage(value=20)
      + g.panel.stat.standardOptions.thresholds.withMode('absolute')
      + g.panel.stat.standardOptions.thresholds.withSteps(throttleThresholds)
      + g.panel.stateTimeline.gridPos.withW(24)
      + g.panel.stateTimeline.gridPos.withH(10)
      + g.panel.stateTimeline.gridPos.withX(0)
      + g.panel.stateTimeline.gridPos.withY(9),

    // Cluster-wide throttling trends
    g.panel.timeSeries.new('Cluster Throttling Trends')
      + g.panel.timeSeries.queryOptions.withTargets([
          g.query.prometheus.new('$PROMETHEUS_DS', 'avg(node_gpu_power_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_power_violation_percentage{cluster_name=~"$cluster_name"})')
          + g.query.prometheus.withLegendFormat('Avg Power Throttling'),
          g.query.prometheus.new('$PROMETHEUS_DS', 'avg(node_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"})')
          + g.query.prometheus.withLegendFormat('Avg Thermal Throttling'),
          g.query.prometheus.new('$PROMETHEUS_DS', 'max(node_gpu_power_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_power_violation_percentage{cluster_name=~"$cluster_name"})')
          + g.query.prometheus.withLegendFormat('Max Power Throttling'),
          g.query.prometheus.new('$PROMETHEUS_DS', 'max(node_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"} or node_amd_gpu_thermal_violation_percentage{cluster_name=~"$cluster_name"})')
          + g.query.prometheus.withLegendFormat('Max Thermal Throttling'),
      ])
      + g.panel.timeSeries.standardOptions.withUnit('percent')
      + g.panel.timeSeries.standardOptions.withDecimals(0)
      + g.panel.timeSeries.options.withLegend({
          calcs: ['mean', 'max'],
          displayMode: 'table',
          placement: 'right',
      })
      + g.panel.timeSeries.gridPos.withW(24)
      + g.panel.timeSeries.gridPos.withH(8)
      + g.panel.timeSeries.gridPos.withX(0)
      + g.panel.timeSeries.gridPos.withY(19),
])
