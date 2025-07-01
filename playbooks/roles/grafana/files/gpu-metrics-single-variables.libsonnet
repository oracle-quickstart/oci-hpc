local g = import './g.libsonnet';
local var = g.dashboard.variable;

{
  prometheus:
    var.datasource.new('PROMETHEUS_DS', 'prometheus')
    + var.datasource.generalOptions.showOnDashboard.withValueOnly(),

  hostname:
    var.query.new('hostname')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('hostname', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  oci_name:
    var.query.new('oci_name')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('oci_name', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  gpu:
    var.query.new('gpu')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('gpu', 'DCGM_FI_DEV_GPU_UTIL')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),
}