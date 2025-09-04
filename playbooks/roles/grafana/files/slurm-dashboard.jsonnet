local g = import './g.libsonnet';
local variables = import './slurm-variables.libsonnet';
local row = g.panel.row;

local slurm_metrics = [
  { expr: 'slurm_node_state_count{state!="RESERVED"}', legend_format: '{{state}}', title: 'Number of nodes by slurm state', unit: 'none' },
  { expr: 'slurm_cpus_total{cluster_name=~"$cluster_name"}', legend_format: '{{cluster_name}}', title: 'Total number of CPUs in a slurm cluster', unit: 'none' },
  { expr: 'slurm_effective_cpus_total{cluster_name=~"$cluster_name"}', legend_format: '{{cluster_name}}', title: 'Total number of effective or schedulable CPUs in a slurm cluster', unit: 'none' },
  { expr: 'slurm_gpus_total{cluster_name=~"$cluster_name"}', legend_format: '{{cluster_name}}', title: 'Total number of GPUs in a slurm cluster', unit: 'none' },
  { expr: 'slurm_partition_jobs_nodes_total{partition=~"$partition"}', legend_format: '{{partition}}', title: 'Total number of Nodes allocated for jobs in a partition', unit: 'none' },
  { expr: 'slurm_partition_jobs_cpus_total{partition=~"$partition"}', legend_format: '{{partition}}', title: 'Total number of CPUs allocated for jobs in a partition', unit: 'none' },
  { expr: 'slurm_partition_jobs_gpus_total{partition=~"$partition"}', legend_format: '{{partition}}', title: 'Total number of GPUs allocated for jobs in a partition', unit: 'none' },
  { expr: 'slurm_active_reservations_nodes_total{reservation=~"$reservation"}', legend_format: '{{reservation}}', title: 'Total number of nodes allocated in a reservation', unit: 'none' },
  { expr: 'slurm_alloc_nodes_user_count{user=~"$user"}', legend_format: '{{user}}', title: 'Total number of allocated nodes for a user', unit: 'none' },
  { expr: 'slurm_alloc_cpus_user_count{user=~"$user"}', legend_format: '{{user}}', title: 'Total number of allocated CPUs for a user', unit: 'none' },
  { expr: 'slurm_alloc_gpus_user_count{user=~"$user"}', legend_format: '{{user}}', title: 'Total number of allocated GPUs for a user', unit: 'none' },
];

local slurm_job_metrics = [
  { expr: 'avg by (slurm_job_id) (slurm_job_gpu_util_percent{slurm_job_id=~"$slurm_job_id"})', legend_format: '{{slurm_job_id}}', title: 'Average job gpu utilization across nodes', unit: 'percent' },
  { expr: 'avg by (slurm_job_id) (slurm_job_gpu_mem_util_percent{slurm_job_id=~"$slurm_job_id"})', legend_format: '{{slurm_job_id}}', title: 'Average job gpu memory utilization across nodes', unit: 'percent' },
  { expr: 'irate(slurm_job_cpu_util_seconds{slurm_job_id=~"$slurm_job_id"}[5m])', legend_format: '{{slurm_job_id}}', title: 'Average job cpu utilization across nodes', unit: 'percent' },
  { expr: 'irate(slurm_job_mem_util_bytes{slurm_job_id=~"$slurm_job_id"}[5m])', legend_format: '{{slurm_job_id}}', title: 'Average job memory utilization across nodes', unit: 'MiB' },  
];

g.dashboard.new('Slurm Dashboard')
+ g.dashboard.withUid('slurm-dashboard')
+ g.dashboard.withDescription(|||
  Dashboard for Slurm Cluster and Slurm Job accounting
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster_name,
  variables.partition,
  variables.reservation,
  variables.user,
  variables.slurm_job_id
])
+ g.dashboard.withPanels(
  g.util.grid.makeGrid([
    row.new('Slurm Cluster')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format)
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in slurm_metrics
      ]),
    row.new('Slurm Job Accounting')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format)
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in slurm_job_metrics
      ]),
  ])
)
