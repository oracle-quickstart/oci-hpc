local g = import './g.libsonnet';
local variables = import './amd-gpu-metrics-single-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';
local gaugePanel = import './gauge-panel.libsonnet';

// Throttling-specific thresholds (lower is better)
local throttleThresholds = [
  g.panel.gauge.thresholdStep.withColor('green') + g.panel.gauge.thresholdStep.withValue(0),
  g.panel.gauge.thresholdStep.withColor('yellow') + g.panel.gauge.thresholdStep.withValue(10),
  g.panel.gauge.thresholdStep.withColor('orange') + g.panel.gauge.thresholdStep.withValue(25),
  g.panel.gauge.thresholdStep.withColor('red') + g.panel.gauge.thresholdStep.withValue(50),
];

g.dashboard.new('AMD GPU Throttling')
+ g.dashboard.withUid('amd-gpu-throttling')
+ g.dashboard.withDescription('AMD GPU Throttling Metrics - Time percentage spent in throttled states')
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-1h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
])
+ g.dashboard.withPanels([
  // Row 0: Gauge panels for current throttling percentages (6 metrics)
  gaugePanel(
    'Power (PPT) %',
    'avg(node_amd_gpu_power_violation_percentage{hostname=~"$hostname"})',
    {w: 4, h: 4, x: 0, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'Thermal %',
    'avg(node_amd_gpu_thermal_violation_percentage{hostname=~"$hostname"})',
    {w: 4, h: 4, x: 4, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'HBM Thermal %',
    'avg(node_amd_gpu_hbm_thermal_violation_percentage{hostname=~"$hostname"})',
    {w: 4, h: 4, x: 8, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'Proc Hot %',
    'avg(node_amd_gpu_processor_hot_violation_percentage{hostname=~"$hostname"})',
    {w: 4, h: 4, x: 12, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'VR Thermal %',
    'avg(node_amd_gpu_vr_thermal_violation_percentage{hostname=~"$hostname"})',
    {w: 4, h: 4, x: 16, y: 0},
    throttleThresholds
  ),
  gaugePanel(
    'Current %',
    'avg(node_amd_gpu_current_violation_percentage{hostname=~"$hostname"})',
    {w: 4, h: 4, x: 20, y: 0},
    throttleThresholds
  ),

  // Row 1: Power Violation Time Series
  timeseriesPanel(
    'Power (PPT) Throttling % Over Time',
    'node_amd_gpu_power_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 4}
  ),

  // Row 2: Thermal Violation Time Series
  timeseriesPanel(
    'Socket Thermal Throttling % Over Time',
    'node_amd_gpu_thermal_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 12}
  ),

  // Row 3: HBM Thermal Violation Time Series
  timeseriesPanel(
    'HBM Thermal Throttling % Over Time',
    'node_amd_gpu_hbm_thermal_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 20}
  ),

  // Row 4: Processor Hot Violation Time Series
  timeseriesPanel(
    'Processor Hot Throttling % Over Time',
    'node_amd_gpu_processor_hot_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 28}
  ),

  // Row 5: VR Thermal Violation Time Series
  timeseriesPanel(
    'VR Thermal Throttling % Over Time',
    'node_amd_gpu_vr_thermal_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 36}
  ),

  // Row 6: Current Violation Time Series
  timeseriesPanel(
    'Current (Amperage) Throttling % Over Time',
    'node_amd_gpu_current_violation_percentage{hostname=~"$hostname"}',
    '{{ hostname }}',
    'percent',
    {w: 24, h: 8, x: 0, y: 44}
  ),

  // Row 7: Combined view of all violations
  g.panel.timeSeries.new('All Throttling Violations Combined')
  + g.panel.timeSeries.queryOptions.withTargets([
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_amd_gpu_power_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Power - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_amd_gpu_thermal_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Thermal - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_amd_gpu_hbm_thermal_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('HBM Thermal - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_amd_gpu_processor_hot_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Proc Hot - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_amd_gpu_vr_thermal_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('VR Thermal - {{ hostname }}'),
    g.query.prometheus.new('$PROMETHEUS_DS', 'node_amd_gpu_current_violation_percentage{hostname=~"$hostname"}')
    + g.query.prometheus.withLegendFormat('Current - {{ hostname }}'),
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
  + g.panel.timeSeries.gridPos.withY(52),
])
