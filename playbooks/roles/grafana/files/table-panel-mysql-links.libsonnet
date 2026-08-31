local g = import './g.libsonnet';

// Table panel for MySQL queries with data link support
//
// Usage:
//   tablePanelMysql(
//     'Title',
//     'SELECT * FROM jobs',
//     {w: 24, h: 10, x: 0, y: 0},
//     columns=[
//       // Single link (backwards compatible):
//       { name: 'Job ID', link: { title: 'View Job', url: '/d/slurm-job-detail?var-job_id=${__value.text}' } },
//       // Multiple links (new):
//       { name: 'Node', links: [
//           { title: 'Host Metrics', url: '/d/host-metrics-single?var-hostname=${__value.text}' },
//           { title: 'GPU Metrics', url: '/d/gpu-metrics-single?var-hostname=${__value.text}' },
//         ]
//       },
//     ]
//   )
//
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
      {
        fieldConfig+: {
          overrides: [
            {
              matcher: { id: 'byName', options: col.name },
              properties:
                (if std.objectHas(col, 'displayName') then
                  [{ id: 'displayName', value: col.displayName }]
                else [])
                + (if std.objectHas(col, 'unit') then
                  [{ id: 'unit', value: col.unit }]
                else [])
                + (if std.objectHas(col, 'links') then
                  [{
                    id: 'links',
                    value: [
                      {
                        title: link.title,
                        url: link.url,
                        targetBlank: std.get(link, 'targetBlank', false),
                      }
                      for link in col.links
                    ],
                  }]
                else if std.objectHas(col, 'link') then
                  [{
                    id: 'links',
                    value: [{
                      title: col.link.title,
                      url: col.link.url,
                      targetBlank: std.get(col.link, 'targetBlank', false),
                    }],
                  }]
                else [])
                + (if std.objectHas(col, 'width') then
                  [{ id: 'custom.width', value: col.width }]
                else [])
                + (if std.get(col, 'hidden', false) then
                  [{ id: 'custom.hidden', value: true }]
                else []),
            }
            for col in columns
          ],
        },
      }
    else {})
