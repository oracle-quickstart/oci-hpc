local g = import './g.libsonnet';
local tablePanel = import './table-panel.libsonnet';

g.dashboard.new('NCCL Traces')
+ g.dashboard.withUid('nccl-traces')
+ g.dashboard.withDescription(|||
  NCCL Profiler Traces
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  g.dashboard.variable.datasource.new('TEMPO_DS', 'tempo'),  
])
+ g.dashboard.withPanels([
  tablePanel(
    'Traces List',
    '$TEMPO_DS',
    '{}',
    {w: 24, h: 12, x: 0, y: 0}
  ),
])