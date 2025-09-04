local g = import '../g.libsonnet';

function(title, promql, gridPos) 
  g.panel.stat.new(title)
    + g.panel.stat.queryOptions.withTargets([
        g.query.prometheus.new(
          '$PROMETHEUS_DS',
          promql,
        )        
      ])
    + g.panel.stat.options.withOrientation('vertical')
    + g.panel.stat.standardOptions.withDisplayName('${__field.labels.gpu}')
    + g.panel.stat.standardOptions.withUnit('none')
    + g.panel.stat.gridPos.withW(gridPos.w)
    + g.panel.stat.gridPos.withH(gridPos.h)
    + g.panel.stat.gridPos.withX(gridPos.x)
    + g.panel.stat.gridPos.withY(gridPos.y)
    + g.panel.stat.options.text.withValueSize(15)
    + g.panel.stat.options.text.withTitleSize(15)    
