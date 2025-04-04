local g = import './g.libsonnet';
local var = g.dashboard.variable;

{
  prometheus:
    var.datasource.new('PROMETHEUS_DS', 'prometheus')
    + var.datasource.generalOptions.showOnDashboard.withValueOnly(),

  compartment:
    var.query.new('compartment')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('compartment', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  hpc_island:
    var.query.new('hpc_island')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('hpc_island', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  rack_id:
    var.query.new('rackID')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('rackID', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  rail_id:
    var.query.new('rail_id')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('rail_id', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  availability_domain:
    var.query.new('AD')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('AD', 'up')
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

  hostname:
    var.query.new('hostname')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('hostname', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  mountpoint:
    var.query.new('mountpoint')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('mountpoint', 'node_filesystem_free_bytes')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  fstype:
    var.query.new('fstype')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('fstype', 'node_filesystem_free_bytes')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  interface:
    var.query.new('interface')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('interface', 'rdma_np_ecn_marked_roce_packets')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  device:
    var.query.new('device')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('device', 'node_network_receive_bytes_total')
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

  cluster:
    var.query.new('cluster_name')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('cluster_name', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),

  fss_mount:
    var.query.new('fss_mount')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + var.query.queryTypes.withLabelValues('fss_mount', 'up')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1),
}
