local g = import './g.libsonnet';
local var = g.dashboard.variable;

{
  prometheus:
    var.datasource.new('PROMETHEUS_DS', 'prometheus')
    + var.datasource.generalOptions.showOnDashboard.withValueOnly(),

  mysql:
    var.datasource.new('MYSQL_DS', 'mysql')
    + var.datasource.generalOptions.showOnDashboard.withNothing(),

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
    + var.query.queryTypes.withLabelValues('partition', 'slurm_node_state')
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

  account_l1:
    var.query.new('account_l1')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('account_l1', 'slurm_account_jobs')
    + var.query.selectionOptions.withIncludeAll(true, '.*')
    + var.query.withRefresh(1),

  slurm_job_id:
    var.query.new('slurm_job_id')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1)
    + var.query.withRegex('/job_id="([^"]+)"/')
    + {
      // Use slurm_job_info from REST exporter (bounded cardinality - running jobs only)
      query: 'query_result(group by (job_id) (slurm_job_info{state="RUNNING"}))',
    },

  user:
    var.query.new('user')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('user', 'slurm_alloc_nodes_user_count')
    + var.query.selectionOptions.withIncludeAll(true, '.*')
    + var.query.withRefresh(1),

  state:
    var.query.new('state')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('state', 'slurm_node_state')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),
}
