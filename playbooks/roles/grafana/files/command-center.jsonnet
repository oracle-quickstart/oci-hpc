local g = import './g.libsonnet';
local variables = import './command-center-variables.libsonnet';
local statPanel = import './stat-panel-single.libsonnet';
g.dashboard.new('Command Center')
+ g.dashboard.withUid('command-center')
+ g.dashboard.withDescription(|||
  Command Center
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster,
])
+ g.dashboard.withPanels([
    statPanel(
      'Total Nodes',
      'count(count by (nodename) (node_uname_info))',
      {w:4, h:4, x:0, y:0}
    ),
    statPanel(
      'Healthy Nodes',
      'count by (cluster_name) (node_health_status{cluster_name=~"$cluster_name"} == 1)',
      {w:4, h:4, x:4, y:0}
    ),
    statPanel(
      'Total GPUs',
      'sum(max by (instance) (DCGM_FI_DEV_COUNT))',
      {w:4, h:4, x:8, y:0}
    ),    
    statPanel(
      'Healthy GPUs',
      'sum by (cluster_name) (available_gpu_count{cluster_name=~"$cluster_name"})',
      {w:4, h:4, x:12, y:0}
    ),
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
    g.panel.stat.new('Compute Node Health')
        + g.panel.stat.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                'node_health_status{cluster_name=~"$cluster_name", hostname!~".*controller.*"}'
            )
        + g.query.prometheus.withLegendFormat('{{hostname}}')
        ])
        + g.panel.stat.standardOptions.withUnit('none')
        + g.panel.stat.options.withTextMode('name')
        + g.panel.stat.options.withColorMode('background')
        + g.panel.stat.options.withGraphMode('none')
        + g.panel.stat.standardOptions.withMappings(
            g.panel.stat.standardOptions.mapping.ValueMap.withType() +  
            g.panel.stat.standardOptions.mapping.ValueMap.withOptions({'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' }})
        )  
        + g.panel.stat.gridPos.withW(24)
        + g.panel.stat.gridPos.withH(5)
        + g.panel.stat.gridPos.withX(0)
        + g.panel.stat.gridPos.withY(4)        
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
              title: 'GPU Metrics',
              url: '/d/gpu-metrics-single/gpu-metrics?var-hostname=${__field.labels.hostname}',
              targetBlank: true,
            },
            {
              title: 'GPU Health',
              url: '/d/gpu-health/gpu-health-status?var-hostname=${__field.labels.hostname}',
              targetBlank: true,
            }

        ]),
    g.panel.stateTimeline.new('Historical Cluster Node Health')
      + g.panel.stateTimeline.queryOptions.withTargets([
          g.query.prometheus.new(
              '$PROMETHEUS_DS',
              'node_health_status',
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
