local g = import '../g.libsonnet';
function(title, promql, legend, gridPos, valueMap={'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' }}) 
  g.panel.stateTimeline.new(title)
    + g.panel.stateTimeline.queryOptions.withTargets([
        g.query.prometheus.new(
            '$PROMETHEUS_DS',
            promql,
        )
        + g.query.prometheus.withLegendFormat(legend)
    ])
    + g.panel.stateTimeline.options.withShowValue('never')
    + g.panel.stateTimeline.options.withPerPage(value=25)
    + g.panel.stat.standardOptions.withMappings(
          g.panel.stat.standardOptions.mapping.ValueMap.withType() +  
          g.panel.stat.standardOptions.mapping.ValueMap.withOptions(valueMap)
    )       
    + g.panel.timeSeries.gridPos.withW(gridPos.w)
    + g.panel.timeSeries.gridPos.withH(gridPos.h)
    + g.panel.timeSeries.gridPos.withX(gridPos.x)
    + g.panel.timeSeries.gridPos.withY(gridPos.y)

