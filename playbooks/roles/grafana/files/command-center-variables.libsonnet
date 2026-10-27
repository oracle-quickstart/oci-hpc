local g = import './g.libsonnet';
local var = g.dashboard.variable;
local memoryClusterQuery = |||
  count by (memory_cluster_id, topology_name) (
    label_replace(
      up{cluster_name=~"$cluster_name", instance=~".*:9100", memory_cluster_id!="None", hostname!~".*controller.*|.*login.*|.*backup.*|.*monitoring.*"},
      "topology_name", "GMF $1", "hostname", ".*-([^-]+)-[^-]+"
    )
    or
    label_replace(
      up{cluster_name=~"$cluster_name", instance=~".*:9100", memory_cluster_id="None", hostname!~".*controller.*|.*login.*|.*backup.*|.*monitoring.*"},
      "topology_name", "Standard", "hostname", ".*"
    )
  )
|||;
local memoryClusterQueryResult =
  'query_result(' + std.strReplace(memoryClusterQuery, '\n', ' ') + ')';

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

  memory_cluster:
    var.query.new('memory_cluster_id')
    + var.query.withDatasourceFromVariable(self.prometheus)
    + {
      definition: memoryClusterQueryResult,
      query: {
        qryType: 3,
        query: memoryClusterQueryResult,
        refId: 'PrometheusVariableQueryEditor-VariableQuery',
      },
    }
    + var.query.withRegex('/memory_cluster_id="(?<value>[^"]+)".*topology_name="(?<text>[^"]+)"/')
    + var.query.selectionOptions.withMulti()
    + var.query.selectionOptions.withIncludeAll()
    + var.query.withRefresh(1)
    + var.query.withSort(3),
}
