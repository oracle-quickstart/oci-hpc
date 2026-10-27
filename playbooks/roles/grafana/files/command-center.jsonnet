local g = import './g.libsonnet';
local variables = import './command-center-variables.libsonnet';
local statPanel = import './stat-panel-single.libsonnet';
local gpuSlots = std.range(1, 18);
local memoryClusterFilter = '$memory_cluster_id';
local computeHostnameFilter = '.*controller.*|.*login.*|.*backup*';
local standardNodeHealthQuery =
  'node_health_status{cluster_name=~"$cluster_name", hostname!~"' + computeHostnameFilter + '"}'
  + ' and on(hostname, cluster_name) up{instance=~".*:9100", memory_cluster_id=~"' + memoryClusterFilter + '", memory_cluster_id="None"}';
local gmfNodeHealthQuery(slot) =
  '('
  + 'node_health_status{cluster_name=~"$cluster_name", hostname!~"' + computeHostnameFilter + '", hostname=~".*-' + std.toString(slot) + '"}'
  + ' and on(hostname, cluster_name) up{instance=~".*:9100", memory_cluster_id=~"' + memoryClusterFilter + '", memory_cluster_id!="None"}'
  + ') or on() ('
  + 'label_replace(vector(-1), "gpu_number", "' + std.toString(slot) + '", "", "")'
  + ' and on() (count(up{cluster_name=~"$cluster_name", instance=~".*:9100", memory_cluster_id=~"' + memoryClusterFilter + '", memory_cluster_id!="None"}) > 0)'
  + ')';
g.dashboard.new('Command Center')
+ g.dashboard.withUid('command-center')
+ g.dashboard.withDescription(|||
  Command Center
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-5m')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster,
  variables.memory_cluster,
])
+ g.dashboard.withPanels([
    statPanel(
      'Total Nodes',
      'count(count by (nodename) (node_uname_info{cluster_name=~"$cluster_name"}))',
      {w:3, h:4, x:0, y:0}
    ),
    statPanel(
      'Management Nodes',
      'count(node_uname_info{hostname=~".*controller*|.*login*|.*backup*"})',
      {w:3, h:4, x:3, y:0}
    ),
    statPanel(
      'Compute Nodes',
      'count(node_health_status{hostname!~".*controller*|.*login*|.*backup*",cluster_name=~"$cluster_name"})',
      {w:3, h:4, x:6, y:0}
    ),
    statPanel(
      'Healthy Nodes',
      'sum(count by (cluster_name) (node_health_status{hostname!~".*controller*|.*login*|.*backup*",cluster_name=~"$cluster_name"} == 1))',
      {w:3, h:4, x:9, y:0}
    ),
    statPanel(
      'Total GPUs',
      'sum(gpu_expected_count{cluster_name=~"$cluster_name"}) or sum(amd_gpu_nodes_total{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:12, y:0}
    ),    
    statPanel(
      'Healthy GPUs',
      'sum(gpu_available_count{cluster_name=~"$cluster_name"}) or sum(amd_gpu_nodes_total{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:16, y:0}
    ),
    statPanel(
      'GPU Memory Fabrics',
      'count(count by (memory_cluster_id) (up{cluster_name=~"$cluster_name", instance=~".*:9100", memory_cluster_id!="None", hostname!~".*controller.*|.*login.*|.*backup.*|.*monitoring.*"})) or vector(0)',
      {w:4, h:4, x:20, y:0}
    ),
    /*
    statPanel(
      'Avg GPU Temp C',
      'avg by (cluster_name) (DCGM_FI_DEV_GPU_TEMP{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:16, y:0}
    ),
    statPanel(
      'Avg GPU Power Util',
      'avg by (cluster_name) (DCGM_FI_DEV_POWER_USAGE{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:20, y:0}
    ),
    */    
    g.panel.stat.new('Compute Node Health - ${memory_cluster_id:text}')
        + g.panel.stat.queryOptions.withTargets(
          [
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                standardNodeHealthQuery
            )
            + g.query.prometheus.withLegendFormat('{{hostname}}')
            + g.query.prometheus.withRefId('A')
          ]
          + [
            g.query.prometheus.new(
              '$PROMETHEUS_DS',
              gmfNodeHealthQuery(slot)
            )
            + g.query.prometheus.withLegendFormat(std.toString(slot))
            + g.query.prometheus.withRefId(std.char(65 + slot))
            for slot in gpuSlots
          ]
        )
        + g.panel.stat.standardOptions.withUnit('none')
        + g.panel.stat.options.withTextMode('name')
        + g.panel.stat.options.withColorMode('background')
        + g.panel.stat.options.withGraphMode('none')
        + g.panel.stat.standardOptions.withMappings(
            g.panel.stat.standardOptions.mapping.ValueMap.withType() +  
            g.panel.stat.standardOptions.mapping.ValueMap.withOptions({'-1': { text: 'missing', color: 'black' },'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' }})
        )  
        + g.panel.stat.gridPos.withW(24)
        + g.panel.stat.gridPos.withH(5)
        + g.panel.stat.gridPos.withX(0)
        + g.panel.stat.gridPos.withY(4)        
        + g.panel.stat.panelOptions.withRepeat('memory_cluster_id')
        + g.panel.stat.panelOptions.withRepeatDirection('h')
        + g.panel.stat.panelOptions.withMaxPerRow(2)
        + g.panel.stat.panelOptions.withLinks([
            {
              title: 'Cluster Metrics',
              url: '/d/cluster-level-metrics/cluster-level-metrics?var-hostname=${__field.labels.cluster_name}',
              targetBlank: true,
            },
            {
              title: 'Multi Node Metrics',
              url: '/d/multi-node-metrics/multi-node-metrics?var-hostname=$__all',
              targetBlank: true,
            }

        ])
        + g.panel.stat.standardOptions.withLinks([
            {
              title: 'Host Metrics',
              url: '/d/host-metrics-single/host-metrics?var-hostname=${__field.labels.hostname}',
              targetBlank: true,
            },
            {
              title: 'Storage Metrics',
              url: '/d/storage-metrics-single/storage-metrics?var-hostname=${__field.labels.hostname}',
              targetBlank: true,
            },
            {
              title: 'GPU Metrics',
              url: '/d/${__field.labels.vendor}-gpu-metrics-single/gpu-metrics?var-hostname=${__field.labels.hostname}',
              targetBlank: true,
            },
            {
              title: 'GPU Health',
              url: '/d/${__field.labels.vendor}-gpu-health/gpu-health-status?var-hostname=${__field.labels.hostname}',
              targetBlank: true,
            },
        ]),
    g.panel.stateTimeline.new('Historical Cluster Node Health')
      + g.panel.stateTimeline.queryOptions.withTargets([
          g.query.prometheus.new(
              '$PROMETHEUS_DS',
              'node_health_status{cluster_name=~"$cluster_name"}',
          )
          + g.query.prometheus.withLegendFormat('{{hostname}}')
      ])
      + g.panel.stateTimeline.options.withShowValue('never')
      + g.panel.stateTimeline.options.withPerPage(value=20)
      + g.panel.stat.standardOptions.withMappings(
            g.panel.stat.standardOptions.mapping.ValueMap.withType() +  
            g.panel.stat.standardOptions.mapping.ValueMap.withOptions({'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' }})
      )       
      + g.panel.stateTimeline.gridPos.withW(24)
      + g.panel.stateTimeline.gridPos.withH(10)
      + g.panel.stat.gridPos.withX(0)
      + g.panel.stat.gridPos.withY(9),
    g.panel.alertList.new('Cluster Alerts')
      + g.panel.alertList.options.UnifiedAlertListOptions.withAlertInstanceLabelFilter('{cluster_name=~"$cluster_name"}')
      + g.panel.alertList.gridPos.withW(24)
      + g.panel.alertList.gridPos.withH(5)
      + g.panel.stat.gridPos.withX(0)
      + g.panel.stat.gridPos.withY(19),      
])
