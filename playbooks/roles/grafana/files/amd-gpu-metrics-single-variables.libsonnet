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
    var.query.new('gpu_id')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('gpu', 'amd_gpu_nodes_total')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  job_id:
    var.query.new('job_id')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('job_id', 'amd_pcie_speed')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),
}