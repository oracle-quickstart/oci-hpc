local g = import '../g.libsonnet';

function(title, promql, gridPos, valueMap={'0': { text: 'Failed', color: 'red' },'1': { text: 'OK', color: 'green' }}) 
  g.panel.stat.new(title)
    + g.panel.stat.queryOptions.withTargets([
        g.query.prometheus.new(
          '$PROMETHEUS_DS',
          promql,
        )        
      ])
    + g.panel.timeSeries.gridPos.withW(gridPos.w)
    + g.panel.timeSeries.gridPos.withH(gridPos.h)
    + g.panel.timeSeries.gridPos.withX(gridPos.x)
    + g.panel.timeSeries.gridPos.withY(gridPos.y)
    + g.panel.stat.options.withGraphMode('none')
    + g.panel.stat.standardOptions.withMappings(
           g.panel.stat.standardOptions.mapping.ValueMap.withType() +  
           g.panel.stat.standardOptions.mapping.ValueMap.withOptions(valueMap)
          )