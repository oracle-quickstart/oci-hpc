local g = import './g.libsonnet';
local tsPanel = import './timeseries-panel.libsonnet';
local row = g.panel.row;
local var = g.dashboard.variable;

// NCCL Inspector job performance dashboard for OTLP mode. Port of the
// upstream template
// (plugins/profiler/inspector/grafana/nccl-inspector-job-performance-template.json),
// adapted to this stack: no cluster selector. Metric names match what
// otelcol's prometheus exporter exposes: the plugin declares bus-bandwidth
// instruments with unit GB/s, which the exporter appends as _GB_per_second
// (verified against otelcol 0.160.0 running with add_metric_suffixes: false;
// the exec-time instruments use unit "us", which sanitizes away). Shows
// per-job bus bandwidth and exec time split by NVLink-only (n_nodes=1) vs
// multi-node, for P2P and collectives.

local busbwColl = 'nccl_bus_bandwidth_gbs_GB_per_second';
local execColl = 'nccl_collective_exec_time_microseconds';
local busbwP2p = 'nccl_p2p_bus_bandwidth_gbs_GB_per_second';
local execP2p = 'nccl_p2p_exec_time_microseconds';

local legendOpts = { displayMode: 'list', placement: 'bottom' };

local promDsVar =
  var.datasource.new('PROMETHEUS_DS', 'prometheus')
  + var.datasource.generalOptions.showOnDashboard.withValueOnly();

local promQueryVar(name, label, query) = {
  name: name,
  label: label,
  type: 'query',
  datasource: { type: 'prometheus', uid: '$PROMETHEUS_DS' },
  query: {
    qryType: 1,
    query: query,
    refId: 'PrometheusVariableQueryEditor-VariableQuery',
  },
  refresh: 2,
  includeAll: true,
  multi: true,
  allValue: '.*',
  current: { selected: true, text: 'All', value: ['$__all'] },
  sort: 1,
};

local nvlinkPanels(busbwMetric, execMetric, filter, y) = [
  tsPanel(
    'BusBw (GBs) NVLink Only ',
    'avg by(message_size, nranks) (' + busbwMetric + '{slurm_job_id=~"$jobid", node=~"$device", ' + filter + ', n_nodes="1"})',
    '__auto',
    'short',
    { w: 12, h: 8, x: 0, y: y },
    legendOpts
  ),
  tsPanel(
    'Exec Time (us) NVLink Only ',
    'avg by(message_size, nranks) (' + execMetric + '{slurm_job_id=~"$jobid", node=~"$device", ' + filter + ', n_nodes="1"})',
    '__auto',
    'short',
    { w: 12, h: 8, x: 12, y: y },
    legendOpts
  ),
  tsPanel(
    'BusBw (GBs) NET Only ',
    'avg by(message_size, nranks, n_nodes) (' + busbwMetric + '{slurm_job_id=~"$jobid", node=~"$device", ' + filter + ', n_nodes!="1"})',
    '__auto',
    'short',
    { w: 12, h: 8, x: 0, y: y + 8 },
    legendOpts
  ),
  tsPanel(
    'Exec Time (us) NET Only ',
    'avg by(message_size, nranks, n_nodes) (' + execMetric + '{slurm_job_id=~"$jobid", node=~"$device", ' + filter + ', n_nodes!="1"})',
    '__auto',
    'short',
    { w: 12, h: 8, x: 12, y: y + 8 },
    legendOpts
  ),
];

local rowPanel(title, y) =
  row.new(title)
  + g.panel.row.gridPos.withW(24)
  + g.panel.row.gridPos.withH(1)
  + g.panel.row.gridPos.withX(0)
  + g.panel.row.gridPos.withY(y);

local expandedRow(title, y, panels) =
  row.new(title)
  + row.withCollapsed(false)
  + g.panel.row.gridPos.withW(24)
  + g.panel.row.gridPos.withH(1)
  + g.panel.row.gridPos.withX(0)
  + g.panel.row.gridPos.withY(y)
  + row.withPanels(panels);

local collFilter(name) = 'collective="' + name + '"';
local p2pFilter(op) = 'p2p_operation="' + op + '"';
local collectiveRow(name, y) =
  [expandedRow(
    'NCCL Inspector - ' + name,
    y,
    nvlinkPanels(busbwColl, execColl, collFilter(name), y + 1)
  )];

g.dashboard.new('NCCL Inspector - Aggregate Metrics (OTLP -> Prometheus)')
+ g.dashboard.withUid('nccl-inspector-job-performance')
+ g.dashboard.withDescription(|||
  NCCL Inspector per-job bus bandwidth and execution time (OTLP mode).
  Select a Slurm job that ran with NCCL_INSPECTOR_OTEL_EXPORT=1.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.time.withFrom('now-24h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  promDsVar,
  promQueryVar(
    'jobid',
    'Slurm Job ID',
    'label_values(nccl_bus_bandwidth_gbs_GB_per_second, slurm_job_id)'
  ),
  promQueryVar(
    'device',
    'Node',
    'label_values(nccl_bus_bandwidth_gbs_GB_per_second{slurm_job_id=~"$jobid"}, node)'
  ),
])
+ g.dashboard.withPanels(
  [rowPanel('NCCL Inspector - P2P [Recv]', 0)]
  + nvlinkPanels(busbwP2p, execP2p, p2pFilter('Recv'), 1)
  + [expandedRow('NCCL Inspector - P2P [Send]', 17, nvlinkPanels(busbwP2p, execP2p, p2pFilter('Send'), 18))]
  + [expandedRow('NCCL Inspector - P2P [SendRecv]', 34, nvlinkPanels(busbwP2p, execP2p, p2pFilter('SendRecv'), 35))]
  + collectiveRow('Broadcast', 51)
  + collectiveRow('Reduce', 68)
  + collectiveRow('ReduceScatter', 85)
  + collectiveRow('AllReduce', 102)
  + collectiveRow('AllGather', 119)
  + collectiveRow('All2All', 136)
  + collectiveRow('AllGatherV', 153)
)
