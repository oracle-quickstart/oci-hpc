local g = import './g.libsonnet';
local variables = import './slurm-variables.libsonnet';
local tablePanelMysql = import './table-panel-mysql-links.libsonnet';

// Time series panel for MySQL queries
local timeseriesPanelMysql(title, sqlQuery, gridPos, maxValue=100) =
  g.panel.timeSeries.new(title)
  + g.panel.timeSeries.queryOptions.withTargets([
      {
        datasource: {
          type: 'mysql',
          uid: 'slurm-mysql',
        },
        rawQueryText: sqlQuery,
        rawSql: sqlQuery,
        refId: 'A',
        format: 'time_series',
      },
    ])
  + g.panel.timeSeries.standardOptions.withUnit('percent')
  + g.panel.timeSeries.standardOptions.withMin(0)
  + (if maxValue == null then {} else g.panel.timeSeries.standardOptions.withMax(maxValue))
  + g.panel.timeSeries.options.withLegend({
      calcs: ['mean', 'max'],
      displayMode: 'table',
      placement: 'right',
    })
  + g.panel.timeSeries.gridPos.withW(gridPos.w)
  + g.panel.timeSeries.gridPos.withH(gridPos.h)
  + g.panel.timeSeries.gridPos.withX(gridPos.x)
  + g.panel.timeSeries.gridPos.withY(gridPos.y);

g.dashboard.new('Slurm Reporting Dashboard')
+ g.dashboard.withUid('slurm-reporting-dashboard')
+ g.dashboard.withDescription(|||
  Historical reporting dashboard for Slurm job data.
  Shows usage trends, resource consumption by account/user, and job statistics.
  Data from MySQL database. Use Grafana time range to filter data.
  Click on Account or User to view jobs in Slurm Job Dashboard.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('')  // No auto-refresh for historical data
+ g.dashboard.time.withFrom('now-30d')
+ g.dashboard.time.withTo('now')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.mysql,
  variables.account_l1,
  variables.user,
])
+ g.dashboard.withPanels([
  // ========================================
  // Row 0: Daily Cluster Usage Summary (y=0, h=10)
  // ========================================
  tablePanelMysql(
    'Daily Cluster Usage',
    |||
      SELECT
        DATE(COALESCE(end_time, start_time, submit_time, updated_at)) as "Date",
        COUNT(*) as "Jobs Submitted",
        SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) as "Completed",
        SUM(CASE WHEN state IN ('FAILED', 'TIMEOUT', 'NODE_FAIL', 'OUT_OF_MEMORY') THEN 1 ELSE 0 END) as "Failed",
        ROUND(100.0 * SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) / COUNT(*), 1) as "Success %",
        ROUND(SUM(elapsed_seconds * num_gpus) / 3600.0, 1) as "GPU Hours",
        ROUND(AVG(avg_gpu_util), 1) as "Avg GPU %",
        ROUND(SUM(elapsed_seconds * num_cpus) / 3600.0, 1) as "Allocated CPU Hours",
        ROUND(
          SUM(avg_cpu_util * num_cpus * elapsed_seconds) /
          NULLIF(SUM(num_cpus * elapsed_seconds), 0),
          1
        ) as "Avg CPU %",
        ROUND(SUM(elapsed_seconds * num_nodes) / 3600.0, 1) as "Node Hours",
        COUNT(DISTINCT `user`) as "Active Users",
        COUNT(DISTINCT account_l1) as "Active Accounts"
      FROM jobs
      WHERE UNIX_TIMESTAMP(COALESCE(end_time, start_time, submit_time, updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
      GROUP BY DATE(COALESCE(end_time, start_time, submit_time, updated_at))
      ORDER BY DATE(COALESCE(end_time, start_time, submit_time, updated_at)) DESC
    |||,
    {w: 24, h: 10, x: 0, y: 0}
  ),

  // ========================================
  // Row 1: Daily Utilization Time Series (y=10, h=8)
  // ========================================
  timeseriesPanelMysql(
    'Daily GPU Utilization',
    |||
      SELECT
        CAST(DATE(COALESCE(end_time, start_time, submit_time, updated_at)) AS DATETIME) as time,
        'Cluster' as metric,
        ROUND(AVG(avg_gpu_util), 1) as value
      FROM jobs
      WHERE UNIX_TIMESTAMP(COALESCE(end_time, start_time, submit_time, updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND avg_gpu_util IS NOT NULL
      GROUP BY CAST(DATE(COALESCE(end_time, start_time, submit_time, updated_at)) AS DATETIME)
      ORDER BY time
    |||,
    {w: 12, h: 8, x: 0, y: 10}
  ),
  timeseriesPanelMysql(
    'Daily CPU Utilization',
    |||
      SELECT
        CAST(DATE(COALESCE(end_time, start_time, submit_time, updated_at)) AS DATETIME) as time,
        'Cluster' as metric,
        ROUND(
          SUM(avg_cpu_util * num_cpus * elapsed_seconds) /
          NULLIF(SUM(num_cpus * elapsed_seconds), 0),
          1
        ) as value
      FROM jobs
      WHERE UNIX_TIMESTAMP(COALESCE(end_time, start_time, submit_time, updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND avg_cpu_util IS NOT NULL
      GROUP BY CAST(DATE(COALESCE(end_time, start_time, submit_time, updated_at)) AS DATETIME)
      ORDER BY time
    |||,
    {w: 12, h: 8, x: 12, y: 10},
    maxValue=null
  ),

  // ========================================
  // Row 2: Account Resource Usage (y=18, h=10)
  // ========================================
  tablePanelMysql(
    'Account Resource Usage',
    |||
      SELECT
        account_l1 as "Account",
        COUNT(*) as "Total Jobs",
        SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) as "Completed",
        SUM(CASE WHEN state IN ('FAILED', 'TIMEOUT', 'NODE_FAIL') THEN 1 ELSE 0 END) as "Failed",
        ROUND(100.0 * SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as "Success %",
        ROUND(SUM(elapsed_seconds * num_gpus) / 3600.0, 1) as "GPU Hours",
        ROUND(AVG(avg_gpu_util), 1) as "Avg GPU %",
        ROUND(SUM(elapsed_seconds * num_cpus) / 3600.0, 1) as "Allocated CPU Hours",
        ROUND(
          SUM(avg_cpu_util * num_cpus * elapsed_seconds) /
          NULLIF(SUM(num_cpus * elapsed_seconds), 0),
          1
        ) as "Avg CPU %",
        ROUND(AVG(elapsed_seconds / 60.0), 1) as "Avg Runtime (min)",
        COUNT(DISTINCT `user`) as "Users"
      FROM jobs
      WHERE UNIX_TIMESTAMP(COALESCE(end_time, start_time, submit_time, updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND account_l1 IS NOT NULL
        AND account_l1 != ''
      GROUP BY account_l1
      ORDER BY SUM(elapsed_seconds * num_gpus) DESC
    |||,
    {w: 24, h: 10, x: 0, y: 18},
    columns=[
      { name: 'Account', link: { title: 'View Jobs for Account', url: '/d/slurm-job-dashboard?var-account_l1=${__value.text}&${__url_time_range}' } },
    ]
  ),

  // ========================================
  // Row 3: Account Utilization Time Series (y=28, h=8)
  // ========================================
  timeseriesPanelMysql(
    'GPU Utilization by Account',
    |||
      SELECT
        CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME) as time,
        j.account_l1 as metric,
        ROUND(AVG(j.avg_gpu_util), 1) as value
      FROM jobs j
      WHERE UNIX_TIMESTAMP(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND j.avg_gpu_util IS NOT NULL
        AND j.account_l1 IS NOT NULL
      GROUP BY CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME), j.account_l1
      ORDER BY time
    |||,
    {w: 12, h: 8, x: 0, y: 28}
  ),
  timeseriesPanelMysql(
    'CPU Utilization by Account',
    |||
      SELECT
        CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME) as time,
        j.account_l1 as metric,
        ROUND(
          SUM(j.avg_cpu_util * j.num_cpus * j.elapsed_seconds) /
          NULLIF(SUM(j.num_cpus * j.elapsed_seconds), 0),
          1
        ) as value
      FROM jobs j
      WHERE UNIX_TIMESTAMP(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND j.avg_cpu_util IS NOT NULL
        AND j.account_l1 IS NOT NULL
      GROUP BY CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME), j.account_l1
      ORDER BY time
    |||,
    {w: 12, h: 8, x: 12, y: 28},
    maxValue=null
  ),

  // ========================================
  // Row 4: User Resource Usage (y=36, h=10)
  // ========================================
  tablePanelMysql(
    'User Resource Usage',
    |||
      SELECT
        `user` as "User",
        account_l1 as "Account",
        COUNT(*) as "Jobs",
        SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) as "Completed",
        SUM(CASE WHEN state IN ('FAILED', 'TIMEOUT') THEN 1 ELSE 0 END) as "Failed",
        ROUND(100.0 * SUM(CASE WHEN state = 'COMPLETED' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 1) as "Success %",
        ROUND(SUM(elapsed_seconds * num_gpus) / 3600.0, 1) as "GPU Hours",
        ROUND(AVG(avg_gpu_util), 1) as "Avg GPU %",
        ROUND(SUM(elapsed_seconds * num_cpus) / 3600.0, 1) as "Allocated CPU Hours",
        ROUND(
          SUM(avg_cpu_util * num_cpus * elapsed_seconds) /
          NULLIF(SUM(num_cpus * elapsed_seconds), 0),
          1
        ) as "Avg CPU %",
        ROUND(AVG(elapsed_seconds / 60.0), 1) as "Avg Runtime (min)"
      FROM jobs
      WHERE UNIX_TIMESTAMP(COALESCE(end_time, start_time, submit_time, updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND `user` IS NOT NULL
      GROUP BY `user`, account_l1
      ORDER BY SUM(elapsed_seconds * num_gpus) DESC
      LIMIT 50
    |||,
    {w: 24, h: 10, x: 0, y: 36},
    columns=[
      { name: 'User', link: { title: 'View Jobs for User', url: '/d/slurm-job-dashboard?var-user=${__value.text}&${__url_time_range}' } },
      { name: 'Account', link: { title: 'View Jobs for Account', url: '/d/slurm-job-dashboard?var-account_l1=${__value.text}&${__url_time_range}' } },
    ]
  ),

  // ========================================
  // Row 5: User Utilization Time Series (y=46, h=8)
  // ========================================
  timeseriesPanelMysql(
    'GPU Utilization by User',
    |||
      SELECT
        CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME) as time,
        j.`user` as metric,
        ROUND(AVG(j.avg_gpu_util), 1) as value
      FROM jobs j
      WHERE UNIX_TIMESTAMP(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND j.avg_gpu_util IS NOT NULL
        AND j.`user` IS NOT NULL
      GROUP BY CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME), j.`user`
      ORDER BY time
    |||,
    {w: 12, h: 8, x: 0, y: 46}
  ),
  timeseriesPanelMysql(
    'CPU Utilization by User',
    |||
      SELECT
        CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME) as time,
        j.`user` as metric,
        ROUND(
          SUM(j.avg_cpu_util * j.num_cpus * j.elapsed_seconds) /
          NULLIF(SUM(j.num_cpus * j.elapsed_seconds), 0),
          1
        ) as value
      FROM jobs j
      WHERE UNIX_TIMESTAMP(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) BETWEEN $__unixEpochFrom() AND $__unixEpochTo()
        AND j.avg_cpu_util IS NOT NULL
        AND j.`user` IS NOT NULL
      GROUP BY CAST(DATE(COALESCE(j.end_time, j.start_time, j.submit_time, j.updated_at)) AS DATETIME), j.`user`
      ORDER BY time
    |||,
    {w: 12, h: 8, x: 12, y: 46},
    maxValue=null
  ),
])
