local g = import './g.libsonnet';
local tablePanelMysql = import './table-panel-mysql.libsonnet';

// NCCL Inspector collective performance dashboard, backed by the
// nccl_inspector_coll_perf MySQL table. Follows the analysis flow of
// NIXT (arXiv 2608.01449): bus bandwidth vs operation sequence number,
// bus bandwidth vs message size, bandwidth distributions, and per-rank
// straggler identification.

local mysqlDS = { type: 'mysql', uid: 'slurm-mysql' };

local sqlTarget(sql, format='table', ref='A') = {
  datasource: mysqlDS,
  rawSql: sql,
  rawQueryText: sql,
  refId: ref,
  format: format,
};

// Grafana variable interpolation happens at query time; jsonnet locals
// must be concatenated into the SQL at build time. When "All" is selected,
// ${var:raw} can render as '', '.*', '$__all' or the literal 'All' depending
// on the Grafana version and allValue.
local allMatch(var) = "'${%s:raw}' IN ('', '.*', '$__all', 'All')" % var;
local regexValues(var) = '${' + var + ':regex}';
local sqlFilter(column, var) =
  '(' + allMatch(var) + " OR CAST(" + column
  + " AS CHAR) REGEXP '^(" + regexValues(var) + ")$')";
local jobFilter = sqlFilter('slurm_job_id', 'jobid');
local commTypeFilter = sqlFilter('comm_type', 'comm_type');
local collFilter = sqlFilter('coll', 'coll');
local msgSizeFilter = sqlFilter('coll_msg_size_bytes', 'msg_size');
local timeFilter =
  'dump_timestamp_us >= ($__from * 1000) AND\n'
  + 'dump_timestamp_us <= ($__to * 1000)';
local baseFilter = jobFilter + " AND\n" + commTypeFilter + " AND\n"
  + collFilter + " AND\n" + timeFilter;

local sqlVar(name, label, query, multi=true) = {
  name: name,
  label: label,
  type: 'query',
  datasource: mysqlDS,
  query: query,
  refresh: 1,
  multi: multi,
  includeAll: true,
  allValue: '.*',
  current: { selected: false, text: 'All', value: '$__all' },
  sort: 1,
};

g.dashboard.new('NCCL Inspector - Operation Details (JSONL -> MySQL)')
+ g.dashboard.withUid('nccl-inspector')
+ g.dashboard.withDescription(|||
  NCCL Inspector collective communication performance (NIXT flow).
  Per-operation records collected from inspector JSON dumps into MySQL.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('1m')
+ g.dashboard.time.withFrom('now-6h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  sqlVar(
    'jobid',
    'Slurm Job',
    'SELECT DISTINCT slurm_job_id FROM nccl_inspector_coll_perf ORDER BY 1 DESC LIMIT 30',
    multi=false
  ),
  sqlVar(
    'comm_type',
    'Comm Type',
    'SELECT DISTINCT comm_type FROM nccl_inspector_coll_perf ORDER BY 1'
  ),
  sqlVar(
    'coll',
    'Collective',
    'SELECT DISTINCT coll FROM nccl_inspector_coll_perf ORDER BY 1'
  ),
  sqlVar(
    'msg_size',
    'Message Size (bytes)',
    'SELECT DISTINCT coll_msg_size_bytes FROM nccl_inspector_coll_perf ORDER BY 1 DESC LIMIT 30'
  ),
])
+ g.dashboard.withPanels([
  // ========================================
  // Row 0: Jobs overview (y=0, h=9)
  // ========================================
  tablePanelMysql(
    'Inspector Jobs',
    |||
      SELECT
        slurm_job_id as "Job",
        comm_type as "Comm Type",
        coll as "Collective",
        COUNT(*) as "Ops",
        MAX(n_ranks) as "Ranks",
        MAX(nnodes) as "Nodes",
         ROUND(AVG(coll_busbw_gbs), 2) as "Avg Bus BW (GB/s)",
        FROM_UNIXTIME(MIN(dump_timestamp_us) / 1000000) as "First Op",
        FROM_UNIXTIME(MAX(dump_timestamp_us) / 1000000) as "Last Op"
      FROM nccl_inspector_coll_perf
      WHERE
    ||| + baseFilter + |||
      GROUP BY 1, 2, 3
      ORDER BY MIN(dump_timestamp_us) DESC
      LIMIT 100
    |||,
    { w: 24, h: 9, x: 0, y: 0 }
  ),

  // ========================================
  // Row 1: Per message-size summary (y=9, h=10)
  // ========================================
  tablePanelMysql(
    'Performance Summary by Message Size',
    |||
      SELECT
        coll_msg_size_bytes as "Msg Size (B)",
        COUNT(*) as "Ops",
        ROUND(AVG(coll_busbw_gbs), 2) as "Avg Bus BW (GB/s)",
        ROUND(MIN(coll_busbw_gbs), 2) as "Min Bus BW",
        ROUND(MAX(coll_busbw_gbs), 2) as "Max Bus BW",
        ROUND(AVG(coll_exec_time_us), 1) as "Avg Exec (us)",
        ROUND(MAX(coll_exec_time_us) / 1000.0, 2) as "Max Exec (ms)"
      FROM nccl_inspector_coll_perf
      WHERE
    ||| + baseFilter + |||
      GROUP BY 1
      ORDER BY 1
    |||,
    { w: 12, h: 10, x: 0, y: 9 }
  ),

  // ========================================
  // Row 1: Bus BW vs message size, NIXT scale view (y=9, h=10)
  // ========================================
  g.panel.xyChart.new('Bus Bandwidth vs Message Size')
  + g.panel.xyChart.queryOptions.withTargets([
      sqlTarget(|||
        SELECT
          coll_msg_size_bytes as "msg_size",
          ROUND(AVG(coll_busbw_gbs), 3) as "avg_busbw"
        FROM nccl_inspector_coll_perf
        WHERE
      ||| + baseFilter + |||
        GROUP BY 1
        ORDER BY 1
      |||)
    ])
  // mapping 'auto': Grafana 13's xychart ignores this grafonnet's manual
  // byIndex series mapping; auto-detect x/y from the 2-column frame.
  + g.panel.xyChart.options.withMapping('auto')
  + g.panel.xyChart.standardOptions.withUnit('short')
  + g.panel.xyChart.gridPos.withW(12)
  + g.panel.xyChart.gridPos.withH(10)
  + g.panel.xyChart.gridPos.withX(12)
  + g.panel.xyChart.gridPos.withY(9),

  // ========================================
  // Row 2: Op sequence scatter, NIXT fig (y=19, h=10)
  // ========================================
  g.panel.xyChart.new('Bus Bandwidth vs Operation Sequence Number')
  + g.panel.xyChart.queryOptions.withTargets([
      sqlTarget(|||
        SELECT
          coll_sn as "coll_sn",
          ROUND(coll_busbw_gbs, 3) as "busbw"
        FROM nccl_inspector_coll_perf
        WHERE
      ||| + baseFilter + " AND\n" + msgSizeFilter + |||
        ORDER BY coll_sn
        LIMIT 5000
      |||)
    ])
  + g.panel.xyChart.options.withMapping('auto')
  + g.panel.xyChart.standardOptions.withUnit('short')
  + g.panel.xyChart.gridPos.withW(24)
  + g.panel.xyChart.gridPos.withH(10)
  + g.panel.xyChart.gridPos.withX(0)
  + g.panel.xyChart.gridPos.withY(19),

  // ========================================
  // Row 3: Bus BW over time per comm type (y=29, h=10)
  // ========================================
  g.panel.timeSeries.new('Bus Bandwidth Over Time')
  + g.panel.timeSeries.queryOptions.withTargets([
      sqlTarget(
        'SELECT\n'
        + '  FROM_UNIXTIME(FLOOR(dump_timestamp_us / 30000000) * 30) as time,\n'
        + '  comm_type as metric,\n'
        + '  ROUND(AVG(coll_busbw_gbs), 3) as value\n'
        + 'FROM nccl_inspector_coll_perf\n'
        + 'WHERE ' + baseFilter + '\n'
        + 'GROUP BY 1, 2\n'
        + 'ORDER BY 1',
        format='time_series'
      )
    ])
  + g.panel.timeSeries.standardOptions.withUnit('short')
  + g.panel.timeSeries.gridPos.withW(12)
  + g.panel.timeSeries.gridPos.withH(10)
  + g.panel.timeSeries.gridPos.withX(0)
  + g.panel.timeSeries.gridPos.withY(29),

  // ========================================
  // Row 3: Bus BW distribution (y=29, h=10)
  // ========================================
  g.panel.histogram.new('Bus Bandwidth Distribution')
  + g.panel.histogram.queryOptions.withTargets([
      sqlTarget(|||
        SELECT coll_busbw_gbs
        FROM nccl_inspector_coll_perf
        WHERE
      ||| + baseFilter + " AND\n" + msgSizeFilter + |||
        LIMIT 20000
      |||)
    ])
  + g.panel.histogram.standardOptions.withUnit('short')
  + g.panel.histogram.gridPos.withW(12)
  + g.panel.histogram.gridPos.withH(10)
  + g.panel.histogram.gridPos.withX(12)
  + g.panel.histogram.gridPos.withY(29),

  // ========================================
  // Row 4: Straggler identification (y=39, h=10)
  // ========================================
  tablePanelMysql(
    'Per-Rank Performance (Stragglers First)',
    |||
      SELECT
        hostname as "Host",
        `rank` as "Rank",
        COUNT(*) as "Ops",
        ROUND(AVG(coll_busbw_gbs), 2) as "Avg Bus BW (GB/s)",
        ROUND(MIN(coll_busbw_gbs), 2) as "Min Bus BW",
        ROUND(AVG(coll_exec_time_us) / 1000.0, 3) as "Avg Exec (ms)",
        ROUND(MAX(coll_exec_time_us) / 1000.0, 2) as "Max Exec (ms)"
      FROM nccl_inspector_coll_perf
      WHERE
    ||| + baseFilter + |||
      GROUP BY 1, 2
      HAVING COUNT(*) > 10
      ORDER BY AVG(coll_busbw_gbs) ASC
      LIMIT 50
    |||,
    { w: 24, h: 10, x: 0, y: 39 }
  ),
])
