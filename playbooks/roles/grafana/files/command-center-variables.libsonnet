local g = import './g.libsonnet';
local var = g.dashboard.variable;

{
  prometheus:
    var.datasource.new('PROMETHEUS_DS', 'prometheus')
    + var.datasource.generalOptions.showOnDashboard.withValueOnly(),

  cluster:
    var.query.new('cluster_name')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('cluster_name', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),
}
