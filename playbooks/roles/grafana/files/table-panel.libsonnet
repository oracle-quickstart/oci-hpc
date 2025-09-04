local g = import './g.libsonnet';

function(title, datasourceUid, query, gridPos) 
  g.panel.table.new(title)
    + g.panel.table.queryOptions.withTargets([
        g.query.tempo.new(
          datasourceUid,
          query,
          []
        )
        + g.query.tempo.withQueryType('traceqlSearch')
        + g.query.tempo.withTableType('traces')
      ])
    + g.panel.table.gridPos.withW(gridPos.w)
    + g.panel.table.gridPos.withH(gridPos.h)
    + g.panel.table.gridPos.withX(gridPos.x)
    + g.panel.table.gridPos.withY(gridPos.y)
    + g.panel.table.options.withShowHeader(true)
    + g.panel.table.options.withCellHeight('sm')
    + g.panel.table.options.footer.withShow(false)