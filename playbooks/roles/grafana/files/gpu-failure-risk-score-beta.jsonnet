local g = import './g.libsonnet';
local variables = import './nvidia-gpu-metrics-single-variables.libsonnet';
local gaugePanel = import './gauge-panel.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';
local var = g.dashboard.variable;

local riskSelector = '{hostname=~"$hostname", oci_name=~"$oci_name", gpu=~"$gpu"}';
local signalSeries(metric, signal) =
  'label_replace(' + metric + riskSelector + ', "signal", "' + signal + '", "hostname", ".*")';

local riskSignalContributorsQuery = std.join(' or ', [
  signalSeries('node_gpu_failure_risk_xid_score', 'xid'),
  signalSeries('node_gpu_failure_risk_pcie_replay_score', 'pcie-replay'),
  signalSeries('node_gpu_failure_risk_pcie_aer_score', 'pcie-aer'),
  signalSeries('node_gpu_failure_risk_dcgm_health_score', 'dcgm-health'),
  signalSeries('node_gpu_failure_risk_power_thermal_score', 'power-thermal'),
  signalSeries('node_gpu_failure_risk_memory_score', 'memory'),
  signalSeries('node_gpu_failure_risk_telemetry_score', 'telemetry'),
]);

local gpuVariable =
  var.query.new('gpu', 'label_values(node_gpu_failure_risk_score{hostname=~"$hostname", oci_name=~"$oci_name"}, gpu)')
  + var.query.withDatasourceFromVariable(variables.prometheus)
  + var.query.selectionOptions.withMulti()
  + var.query.selectionOptions.withIncludeAll()
  + var.query.withRefresh(1)
  + var.query.withSort(3);

local riskThresholds = [
  g.panel.gauge.thresholdStep.withColor('green') + g.panel.gauge.thresholdStep.withValue(0),
  g.panel.gauge.thresholdStep.withColor('yellow') + g.panel.gauge.thresholdStep.withValue(30),
  g.panel.gauge.thresholdStep.withColor('orange') + g.panel.gauge.thresholdStep.withValue(60),
  g.panel.gauge.thresholdStep.withColor('red') + g.panel.gauge.thresholdStep.withValue(85),
];

g.dashboard.new('GPU Failure Risk Score (beta)')
+ g.dashboard.withUid('gpu-failure-risk-score-beta')
+ g.dashboard.withDescription(|||
  Per-GPU NVIDIA failure risk score derived from current DCGM, PCIe, thermal, and memory reliability signals.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-1h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
  variables.oci_name,
  gpuVariable,
])
+ g.dashboard.withPanels([
  gaugePanel(
    'Failure Risk - GPU $gpu',
    'node_gpu_failure_risk_score' + riskSelector,
    {w: 6, h: 8, x: 0, y: 0},
    riskThresholds
  )
  + g.panel.gauge.panelOptions.withRepeat('gpu')
  + g.panel.gauge.panelOptions.withRepeatDirection('h')
  + g.panel.gauge.panelOptions.withMaxPerRow(4),

  timeseriesPanel(
    'Risk Signal Contributors',
    riskSignalContributorsQuery,
    '{{ signal }} GPU {{ gpu }}',
    'percent',
    {w: 24, h: 9, x: 0, y: 8},
    {
      calcs: ['lastNotNull', 'max'],
      displayMode: 'table',
      placement: 'right',
    }
  ),
])
