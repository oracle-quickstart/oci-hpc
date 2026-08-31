local g = import './g.libsonnet';

// Table panel for MySQL queries (Slurm job reporting)
function(title, sqlQuery, gridPos, columns=[])
  g.panel.table.new(title)
  + g.panel.table.queryOptions.withTargets([
      {
        datasource: {
          type: 'mysql',
          uid: 'slurm-mysql',
        },
        rawQueryText: sqlQuery,
        rawSql: sqlQuery,
        refId: 'A',
        format: 'table',
      },
    ])
  + g.panel.table.gridPos.withW(gridPos.w)
  + g.panel.table.gridPos.withH(gridPos.h)
  + g.panel.table.gridPos.withX(gridPos.x)
  + g.panel.table.gridPos.withY(gridPos.y)
  + (if std.length(columns) > 0 then
       g.panel.table.fieldConfig.overrides.withOverrides(
         [
           {
             matcher: { id: 'byName', options: col.name },
             properties: [
               { id: 'displayName', value: col.displayName },
             ] + (if std.objectHas(col, 'unit') then [{ id: 'unit', value: col.unit }] else []),
           }
           for col in columns
         ]
       )
     else {})
