local g = import '../g.libsonnet';

function(title, promql, legend, unit, gridPos, legendOptions={
  calcs: ['p99', 'p95', 'p90'],
  displayMode: 'table',
  placement: 'right',
})
  local targets =
    if std.type(promql) == 'array' then
      assert std.type(legend) == 'array' && std.length(promql) == std.length(legend) :
        'promql and legend arrays must have the same length';
      [
        g.query.prometheus.new(
          '$PROMETHEUS_DS',
          promql[i],
        )
        + g.query.prometheus.withLegendFormat(legend[i])
        for i in std.range(0, std.length(promql) - 1)
      ]
    else
      [
        g.query.prometheus.new(
          '$PROMETHEUS_DS',
          promql,
        )
        + g.query.prometheus.withLegendFormat(legend)
      ];
  g.panel.timeSeries.new(title)
    + g.panel.timeSeries.queryOptions.withTargets(targets)
    + g.panel.timeSeries.standardOptions.withUnit(unit)
    + g.panel.timeSeries.options.withLegend(value=legendOptions)
    + g.panel.timeSeries.gridPos.withW(gridPos.w)
    + g.panel.timeSeries.gridPos.withH(gridPos.h)
    + g.panel.timeSeries.gridPos.withX(gridPos.x)
    + g.panel.timeSeries.gridPos.withY(gridPos.y)
