local g = import '../g.libsonnet';

function(title, promql, gridPos) 
  g.panel.gauge.new(title)
    + g.panel.gauge.queryOptions.withTargets([
        g.query.prometheus.new(
          '$PROMETHEUS_DS',
          promql,
        )        
      ])
    + g.panel.gauge.gridPos.withW(gridPos.w)
    + g.panel.gauge.gridPos.withH(gridPos.h)
    + g.panel.gauge.gridPos.withX(gridPos.x)
    + g.panel.gauge.gridPos.withY(gridPos.y)
    + g.panel.gauge.standardOptions.withUnit('percent')

