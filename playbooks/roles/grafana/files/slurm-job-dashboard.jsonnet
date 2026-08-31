local g = import './g.libsonnet';
local variables = import './slurm-variables.libsonnet';
local tablePanelMysql = import './table-panel-mysql-links.libsonnet';

g.dashboard.new('Slurm Job Dashboard')
+ g.dashboard.withUid('slurm-job-dashboard')
+ g.dashboard.withDescription(|||
  Dashboard for Slurm job monitoring.
  Shows failed, running, and completed jobs.
  Use Account and User filters to narrow results.
  Click on Job ID to view detailed job performance.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-1h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.mysql,
  variables.cluster_name,
  variables.account_l1,
  variables.user,
])
+ g.dashboard.withPanels([
  // ========================================
  // Row 0: Failed Jobs (y=0, h=12)
  // ========================================
  tablePanelMysql(
    'Failed Jobs',
    |||
      SELECT
        job_id as "Job ID",
        name as "Name",
        `user` as "User",
        account_l1 as "Account",
        `partition` as "Partition",
        state as "State",
        exit_code as "Exit Code",
        num_nodes as "Nodes",
        num_gpus as "GPUs",
        ROUND(elapsed_seconds / 60.0, 1) as "Runtime (min)",
        submit_time as "Submitted",
        end_time as "Ended",
        UNIX_TIMESTAMP(COALESCE(start_time, submit_time)) * 1000 as "start_ms",
        UNIX_TIMESTAMP(COALESCE(end_time, NOW())) * 1000 as "end_ms"
      FROM jobs
      WHERE state IN ('FAILED', 'TIMEOUT', 'NODE_FAIL', 'OUT_OF_MEMORY', 'CANCELLED')
        AND $__timeFilter(submit_time)
        AND ('${account_l1:raw}' IN ('', '.*', '$__all') OR account_l1 = '${account_l1:raw}')
        AND ('${user:raw}' IN ('', '.*', '$__all') OR `user` = '${user:raw}')
      ORDER BY submit_time DESC
      LIMIT 100
    |||,
    {w: 24, h: 12, x: 0, y: 0},
    columns=[
      { name: 'Job ID', link: { title: 'View Job Details', url: '/d/slurm-job-detail?var-job_id=${__value.text}&from=${__data.fields.start_ms}&to=${__data.fields.end_ms}' } },
      { name: 'start_ms', hidden: true },
      { name: 'end_ms', hidden: true },
    ]
  ),

  // ========================================
  // Row 1: Running Jobs (y=12, h=14)
  // ========================================
  tablePanelMysql(
    'Running Jobs',
    |||
      SELECT
        j.job_id as "Job ID",
        j.name as "Name",
        j.`user` as "User",
        j.account_l1 as "Account",
        j.`partition` as "Partition",
        j.num_nodes as "Nodes",
        j.num_gpus as "GPUs",
        ROUND(COALESCE(u.avg_gpu, 0), 1) as "Avg GPU %",
        ROUND(COALESCE(u.avg_cpu, 0) / NULLIF(j.num_cpus, 0), 1) as "Avg CPU %",
        ROUND(COALESCE(u.avg_mem_percent, 0), 1) as "Mem %",
        j.start_time as "Started",
        ROUND(TIMESTAMPDIFF(SECOND, j.start_time, NOW()) / 60, 1) as "Runtime (min)",
        UNIX_TIMESTAMP(COALESCE(j.start_time, j.submit_time, DATE_SUB(NOW(), INTERVAL 5 MINUTE))) * 1000 as "start_ms",
        UNIX_TIMESTAMP(NOW()) * 1000 as "end_ms"
      FROM jobs j
      LEFT JOIN (
        SELECT
          job_id,
          AVG(gpu_util) as avg_gpu,
          AVG(cpu_util) as avg_cpu,
          AVG(mem_util_percent) as avg_mem_percent
        FROM job_utilization
        WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 15 MINUTE)
        GROUP BY job_id
      ) u ON j.job_id = u.job_id
      WHERE j.state = 'RUNNING'
        AND ('${account_l1:raw}' IN ('', '.*', '$__all') OR j.account_l1 = '${account_l1:raw}')
        AND ('${user:raw}' IN ('', '.*', '$__all') OR j.`user` = '${user:raw}')
      ORDER BY j.num_nodes DESC, j.start_time DESC
      LIMIT 100
    |||,
    {w: 24, h: 14, x: 0, y: 12},
    columns=[
      { name: 'Job ID', link: { title: 'View Job Details', url: '/d/slurm-job-detail?var-job_id=${__value.text}&from=${__data.fields.start_ms}&to=now' } },
      { name: 'start_ms', hidden: true },
      { name: 'end_ms', hidden: true },
    ]
  ),

  // ========================================
  // Row 2: Completed Jobs (y=26, h=12)
  // ========================================
  tablePanelMysql(
    'Completed Jobs (Last 24h)',
    |||
      SELECT
        job_id as "Job ID",
        name as "Name",
        `user` as "User",
        account_l1 as "Account",
        state as "State",
        num_nodes as "Nodes",
        num_gpus as "GPUs",
        ROUND(elapsed_seconds / 60.0, 1) as "Runtime (min)",
        ROUND(avg_gpu_util, 1) as "Avg GPU %",
        ROUND(max_gpu_util, 1) as "Max GPU %",
        end_time as "Ended",
        UNIX_TIMESTAMP(COALESCE(start_time, submit_time)) * 1000 as "start_ms",
        UNIX_TIMESTAMP(COALESCE(end_time, NOW())) * 1000 as "end_ms"
      FROM jobs
      WHERE state = 'COMPLETED'
        AND end_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        AND ('${account_l1:raw}' IN ('', '.*', '$__all') OR account_l1 = '${account_l1:raw}')
        AND ('${user:raw}' IN ('', '.*', '$__all') OR `user` = '${user:raw}')
      ORDER BY end_time DESC
      LIMIT 100
    |||,
    {w: 24, h: 12, x: 0, y: 26},
    columns=[
      { name: 'Job ID', link: { title: 'View Job Details', url: '/d/slurm-job-detail?var-job_id=${__value.text}&from=${__data.fields.start_ms}&to=${__data.fields.end_ms}' } },
      { name: 'start_ms', hidden: true },
      { name: 'end_ms', hidden: true },
    ]
  ),
])
