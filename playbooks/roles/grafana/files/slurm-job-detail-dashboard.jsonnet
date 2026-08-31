local g = import './g.libsonnet';
local variables = import './slurm-variables.libsonnet';
local tablePanelMysql = import './table-panel-mysql-links.libsonnet';

// Stat panel for numeric MySQL values
local statPanelMysql(title, sqlQuery, gridPos, unit='none') =
  g.panel.stat.new(title)
  + g.panel.stat.queryOptions.withTargets([
      {
        datasource: { type: 'mysql', uid: 'slurm-mysql' },
        rawSql: sqlQuery,
        format: 'table',
        refId: 'A',
      },
    ])
  + g.panel.stat.standardOptions.withUnit(unit)
  + g.panel.stat.options.withGraphMode('none')
  + g.panel.stat.options.withColorMode('none')
  + g.panel.stat.options.withTextMode('value')
  + g.panel.stat.options.reduceOptions.withCalcs(['lastNotNull'])
  + g.panel.stat.gridPos.withW(gridPos.w)
  + g.panel.stat.gridPos.withH(gridPos.h)
  + g.panel.stat.gridPos.withX(gridPos.x)
  + g.panel.stat.gridPos.withY(gridPos.y);

// Stat panel for text/string MySQL values - uses values mode instead of calcs
local statPanelMysqlText(title, sqlQuery, gridPos) =
  g.panel.stat.new(title)
  + g.panel.stat.queryOptions.withTargets([
      {
        datasource: { type: 'mysql', uid: 'slurm-mysql' },
        rawSql: sqlQuery,
        format: 'table',
        refId: 'A',
      },
    ])
  + g.panel.stat.options.withGraphMode('none')
  + g.panel.stat.options.withColorMode('none')
  + g.panel.stat.options.withTextMode('value')
  + g.panel.stat.options.reduceOptions.withCalcs([])
  + g.panel.stat.options.reduceOptions.withValues(true)
  + g.panel.stat.options.reduceOptions.withFields('/.*/')
  + g.panel.stat.options.reduceOptions.withLimit(1)
  + g.panel.stat.gridPos.withW(gridPos.w)
  + g.panel.stat.gridPos.withH(gridPos.h)
  + g.panel.stat.gridPos.withX(gridPos.x)
  + g.panel.stat.gridPos.withY(gridPos.y);

// Time series panel for MySQL (NVML exporter data stored in job_utilization)
local timeseriesPanelMysql(title, sqlQuery, gridPos, unit='percent') =
  g.panel.timeSeries.new(title)
  + g.panel.timeSeries.queryOptions.withTargets([
      {
        datasource: { type: 'mysql', uid: 'slurm-mysql' },
        rawSql: sqlQuery,
        format: 'time_series',
        refId: 'A',
      },
    ])
  + g.panel.timeSeries.standardOptions.withUnit(unit)
  + g.panel.timeSeries.gridPos.withW(gridPos.w)
  + g.panel.timeSeries.gridPos.withH(gridPos.h)
  + g.panel.timeSeries.gridPos.withX(gridPos.x)
  + g.panel.timeSeries.gridPos.withY(gridPos.y);

// Job ID variable for this dashboard
local jobIdVar =
  g.dashboard.variable.textbox.new('job_id', default='')
  + g.dashboard.variable.textbox.generalOptions.withLabel('Job ID');

g.dashboard.new('Slurm Job Detail')
+ g.dashboard.withUid('slurm-job-detail')
+ g.dashboard.withDescription(|||
  Detailed performance view for a single Slurm job.
  Shows job info and utilization over time from NVML exporter data.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-1h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.mysql,
  jobIdVar,
])
+ g.dashboard.withPanels([
  // ========================================
  // Row 0: Job Info Stats
  // ========================================
  statPanelMysqlText(
    'Job Name',
    'SELECT name FROM jobs WHERE job_id = ${job_id}',
    {w: 4, h: 3, x: 0, y: 0}
  ),
  statPanelMysqlText(
    'User',
    'SELECT `user` FROM jobs WHERE job_id = ${job_id}',
    {w: 3, h: 3, x: 4, y: 0}
  ),
  statPanelMysqlText(
    'Account',
    'SELECT account_l1 FROM jobs WHERE job_id = ${job_id}',
    {w: 3, h: 3, x: 7, y: 0}
  ),
  statPanelMysqlText(
    'State',
    'SELECT state FROM jobs WHERE job_id = ${job_id}',
    {w: 2, h: 3, x: 10, y: 0}
  ),
  statPanelMysql(
    'Nodes',
    'SELECT num_nodes FROM jobs WHERE job_id = ${job_id}',
    {w: 2, h: 3, x: 12, y: 0}
  ),
  statPanelMysql(
    'CPUs',
    'SELECT num_cpus FROM jobs WHERE job_id = ${job_id}',
    {w: 2, h: 3, x: 14, y: 0}
  ),
  statPanelMysql(
    'GPUs',
    'SELECT num_gpus FROM jobs WHERE job_id = ${job_id}',
    {w: 2, h: 3, x: 16, y: 0}
  ),
  statPanelMysqlText(
    'Partition',
    'SELECT `partition` FROM jobs WHERE job_id = ${job_id}',
    {w: 3, h: 3, x: 18, y: 0}
  ),
  statPanelMysql(
    'Runtime',
    |||
      SELECT
        CASE
          WHEN state = 'RUNNING' THEN ROUND(TIMESTAMPDIFF(SECOND, start_time, NOW()) / 60, 1)
          ELSE ROUND(elapsed_seconds / 60, 1)
        END
      FROM jobs WHERE job_id = ${job_id}
    |||,
    {w: 3, h: 3, x: 21, y: 0},
    'min'
  ),

  // ========================================
  // Row 1: GPU Utilization Over Time (NVML exporter data)
  // ========================================
  timeseriesPanelMysql(
    'GPU Utilization',
    |||
      SELECT
        timestamp as time,
        CONCAT(hostname, ' GPU', gpu_index) as metric,
        gpu_util as value
      FROM job_utilization
      WHERE job_id = ${job_id}
        AND gpu_index >= 0
        AND $__timeFilter(timestamp)
      ORDER BY timestamp
    |||,
    {w: 12, h: 10, x: 0, y: 3}
  ),
  timeseriesPanelMysql(
    'GPU Memory',
    |||
      SELECT
        timestamp as time,
        CONCAT(hostname, ' GPU', gpu_index) as metric,
        gpu_mem_util as value
      FROM job_utilization
      WHERE job_id = ${job_id}
        AND gpu_index >= 0
        AND $__timeFilter(timestamp)
      ORDER BY timestamp
    |||,
    {w: 12, h: 10, x: 12, y: 3}
  ),

  // ========================================
  // Row 2: CPU/Memory Utilization Over Time (NVML exporter data)
  // ========================================
  timeseriesPanelMysql(
    'CPU Utilization',
    |||
      SELECT
        ju.timestamp as time,
        ju.hostname as metric,
        ROUND(ju.cpu_util / NULLIF(j.num_cpus, 0), 1) as value
      FROM job_utilization ju
      JOIN jobs j ON ju.job_id = j.job_id
      WHERE ju.job_id = ${job_id}
        AND $__timeFilter(ju.timestamp)
      ORDER BY ju.timestamp
    |||,
    {w: 12, h: 10, x: 0, y: 13}
  ),
  timeseriesPanelMysql(
    'Memory Utilization',
    |||
      SELECT
        timestamp as time,
        hostname as metric,
        mem_util_percent as value
      FROM job_utilization
      WHERE job_id = ${job_id}
        AND $__timeFilter(timestamp)
      ORDER BY timestamp
    |||,
    {w: 12, h: 10, x: 12, y: 13}
  ),

  // ========================================
  // Row 3: Per-Node Breakdown (with link to GPU metrics)
  // ========================================
  tablePanelMysql(
    'Per-Node Breakdown',
    |||
      SELECT
        ju.hostname as "Node",
        'CPU' as "CPU Dashboards",
        CASE MAX(CASE WHEN ju.gpu_vendor IN (1, 2) THEN ju.gpu_vendor END)
          WHEN 1 THEN 'NVIDIA'
          WHEN 2 THEN 'AMD'
          ELSE NULL
        END as "GPU Dashboards",
        COUNT(DISTINCT CASE WHEN ju.gpu_index >= 0 THEN ju.gpu_index END) as "GPUs",
        ROUND(AVG(ju.gpu_util), 1) as "Avg GPU %",
        ROUND(MAX(ju.gpu_util), 1) as "Max GPU %",
        ROUND(AVG(ju.gpu_mem_util), 1) as "Avg GPU Mem %",
        ROUND(AVG(ju.cpu_util) / NULLIF(j.num_cpus, 0), 1) as "CPU %",
        ROUND(AVG(ju.mem_util_percent), 1) as "Mem %",
        COUNT(*) as "Samples",
        CASE MAX(CASE WHEN ju.gpu_vendor IN (1, 2) THEN ju.gpu_vendor END)
          WHEN 1 THEN 'nvidia'
          WHEN 2 THEN 'amd'
          ELSE ''
        END as "Vendor",
        UNIX_TIMESTAMP(
          DATE_SUB(
            MIN(COALESCE(j.start_time, j.submit_time, DATE_SUB(NOW(), INTERVAL 5 MINUTE))),
            INTERVAL 5 MINUTE
          )
        ) * 1000 as "link_start_ms",
        UNIX_TIMESTAMP(
          DATE_ADD(COALESCE(MAX(j.end_time), NOW()), INTERVAL 5 MINUTE)
        ) * 1000 as "link_end_ms"
      FROM job_utilization ju
      JOIN jobs j ON ju.job_id = j.job_id
      WHERE ju.job_id = ${job_id}
        AND $__timeFilter(ju.timestamp)
      GROUP BY ju.hostname, j.num_cpus
      ORDER BY ju.hostname
    |||,
    {w: 24, h: 8, x: 0, y: 23},
    columns=[
      { name: 'Node', width: 145 },
      { name: 'CPU Dashboards', displayName: 'CPU', width: 80, links: [
          { title: 'Host Metrics', url: '/d/host-metrics-single?var-hostname=${__data.fields.Node}&from=${__data.fields.link_start_ms}&to=${__data.fields.link_end_ms}' },
          { title: 'Storage Metrics', url: '/d/storage-metrics-single?var-hostname=${__data.fields.Node}&from=${__data.fields.link_start_ms}&to=${__data.fields.link_end_ms}' },
        ]
      },
      { name: 'GPU Dashboards', displayName: 'GPU', width: 90, links: [
          { title: 'GPU Metrics', url: '/d/${__data.fields.Vendor}-gpu-metrics-single/gpu-metrics?var-hostname=${__data.fields.Node}&from=${__data.fields.link_start_ms}&to=${__data.fields.link_end_ms}' },
          { title: 'GPU Health', url: '/d/${__data.fields.Vendor}-gpu-health/gpu-health-status?var-hostname=${__data.fields.Node}&from=${__data.fields.link_start_ms}&to=${__data.fields.link_end_ms}' },
        ]
      },
      { name: 'GPUs', width: 60 },
      { name: 'Avg GPU %', width: 95 },
      { name: 'Max GPU %', width: 95 },
      { name: 'Avg GPU Mem %', width: 110 },
      { name: 'CPU %', width: 75 },
      { name: 'Mem %', width: 75 },
      { name: 'Samples', width: 80 },
      { name: 'Vendor', filterable: false, hidden: true },
      { name: 'link_start_ms', filterable: false, hidden: true },
      { name: 'link_end_ms', filterable: false, hidden: true },
    ]
  ),
])
