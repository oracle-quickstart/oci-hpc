local g = import './g.libsonnet';
local variables = import './nvidia-gpu-metrics-single-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';
local gaugePanel = import './gauge-panel.libsonnet';

// Throttling-specific thresholds (lower is better)
local throttleThresholds = [
  g.panel.gauge.thresholdStep.withColor('green') + g.panel.gauge.thresholdStep.withValue(0),
  g.panel.gauge.thresholdStep.withColor('yellow') + g.panel.gauge.thresholdStep.withValue(10),
  g.panel.gauge.thresholdStep.withColor('orange') + g.panel.gauge.thresholdStep.withValue(25),
  g.panel.gauge.thresholdStep.withColor('red') + g.panel.gauge.thresholdStep.withValue(50),
];

g.dashboard.new('NVIDIA GPU Throttling')
+ g.dashboard.withUid('nvidia-gpu-throttling')
+ g.dashboard.withDescription('NVIDIA GPU Throttling Metrics - Time percentage spent in throttled states')
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-1h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
])
+ g.dashboard.withPanels([
  // Row 0: Gauge panels for current throttling percentages
  gaugePanel(
    'Power Throttling %',
    'avg(node_gpu_power_violation_percentage{hostname=~"$hostname"})',
    {w: 5, h: 4, x: 0, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'Thermal Throttling %',
    'avg(node_gpu_thermal_violation_percentage{hostname=~"$hostname"})',
    {w: 5, h: 4, x: 5, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'Board Limit %',
    'avg(node_gpu_board_limit_violation_percentage{hostname=~"$hostname"})',
    {w: 5, h: 4, x: 10, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'Sync Boost %',
    'avg(node_gpu_sync_boost_violation_percentage{hostname=~"$hostname"})',
    {w: 5, h: 4, x: 15, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'Reliability %',
    'avg(node_gpu_reliability_violation_percentage{hostname=~"$hostname"})',
    {w: 4, h: 4, x: 20, y: 0},
    throttleThresholds
  ),

  // Row 1: Power Violation Time Series
  timeseriesPanel(
    'Power Throttling % Over Time',
    'node_gpu_power_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 4}
  ),

  // Row 2: Thermal Violation Time Series
  timeseriesPanel(
    'Thermal Throttling % Over Time',
    'node_gpu_thermal_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 12}
  ),

  // Row 3: Board Limit Violation Time Series
  timeseriesPanel(
    'Board Limit Throttling % Over Time',
    'node_gpu_board_limit_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 20}
  ),

  // Row 4: Sync Boost Violation Time Series
  timeseriesPanel(
    'Sync Boost Throttling % Over Time',
    'node_gpu_sync_boost_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 28}
  ),

  // Row 5: Reliability Violation Time Series
  timeseriesPanel(
    'Reliability Throttling % Over Time',
    'node_gpu_reliability_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 36}
  ),

  // Row 6: Combined view of all violations
  g.panel.timeSeries.new('All Throttling Violations Combined')
  + g.panel.timeSeries.queryOptions.withTargets([
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_gpu_power_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Power - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_gpu_thermal_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Thermal - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_gpu_board_limit_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Board Limit - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_gpu_sync_boost_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Sync Boost - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_gpu_reliability_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Reliability - {{ hostname }}'),
  ])
  + g.panel.timeSeries.standardOptions.withUnit('percent')
  + g.panel.timeSeries.standardOptions.withDecimals(0)
  + g.panel.timeSeries.options.withLegend({
    calcs: ['mean', 'max'],
    displayMode: 'table',
    placement: 'right',
  })
  + g.panel.timeSeries.gridPos.withW(24)
  + g.panel.timeSeries.gridPos.withH(10)
  + g.panel.timeSeries.gridPos.withX(0)
  + g.panel.timeSeries.gridPos.withY(44),
])
