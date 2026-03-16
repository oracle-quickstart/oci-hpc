local g = import './g.libsonnet';
local var = g.dashboard.variable;

{
  prometheus:
    var.datasource.new('PROMETHEUS_DS', 'prometheus')
    + var.datasource.generalOptions.showOnDashboard.withValueOnly(),

  cluster_name:
    var.query.new('cluster_name')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('cluster_name', 'slurm_cpus_total')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  partition:
    var.query.new('partition')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('partition', 'slurm_partition_jobs_cpus_total')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  reservation:
    var.query.new('reservation')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('reservation', 'slurm_active_reservations_cores_total')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),
  
  slurm_job_id:
    var.query.new('slurm_job_id')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1)
    + var.query.withRegex('/slurm_job_id="([^"]+)"/')
    + {
      query: 'query_result(group by (slurm_job_id) (slurm_job_cpu_util_seconds) or group by (slurm_job_id) (label_replace(amd_gpu_gfx_activity, "slurm_job_id", "$1", "job_id", "(.*)")))',
    },
    
  user:
    var.query.new('user')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('user', 'slurm_alloc_nodes_user_count')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),
}
