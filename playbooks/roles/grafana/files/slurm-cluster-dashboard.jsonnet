local g = import './g.libsonnet';
local variables = import './slurm-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';
local statPanelSingle = import './stat-panel-single.libsonnet';

// Table panel for Prometheus with data links
local tablePanelPrometheus(title, promql, gridPos, columns=[]) =
  g.panel.table.new(title)
  + g.panel.table.queryOptions.withTargets([
      g.query.prometheus.new('$PROMETHEUS_DS', promql)
      + g.query.prometheus.withInstant(true)
      + g.query.prometheus.withFormat('table'),
    ])
  + g.panel.table.queryOptions.withTransformations([
      {
        id: 'organize',
        options: {
          excludeByName: {
            Time: true,
            Value: true,
            __name__: true,
          },
          renameByName: {
            node: 'Node',
            partition: 'Partition',
            state: 'State',
            vendor: 'Vendor',
            gpus: 'GPUs',
            cpus: 'CPUs',
            mem: 'Memory',
            load_alloc: 'Alloc',
            load_total: 'Total',
            features: 'Features',
          },
        },
      },
    ])
  + g.panel.table.gridPos.withW(gridPos.w)
  + g.panel.table.gridPos.withH(gridPos.h)
  + g.panel.table.gridPos.withX(gridPos.x)
  + g.panel.table.gridPos.withY(gridPos.y)
  + (if std.length(columns) > 0 then
      {
        fieldConfig+: {
          overrides: [
            {
              matcher: { id: 'byName', options: col.name },
              properties:
                (if std.objectHas(col, 'width') then
                  [{ id: 'custom.width', value: col.width }]
                else [])
                + (if std.objectHas(col, 'link') then
                  [{
                    id: 'links',
                    value: [{
                      title: col.link.title,
                      url: col.link.url,
                      targetBlank: std.get(col.link, 'targetBlank', false),
                    }],
                  }]
                else []),
            }
            for col in columns
          ],
        },
      }
    else {});

g.dashboard.new('Slurm Cluster Dashboard')
+ g.dashboard.withUid('slurm-cluster-dashboard')
+ g.dashboard.withDescription(|||
  Slurm cluster overview dashboard.
  Shows node status, job counts, and resource allocation by reservation, account, and user.
  Uses slurm_node_state from sinfo for per-node state tracking.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-1h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster_name,
  variables.partition,
  variables.reservation,
  variables.account_l1,
  variables.user,
])
+ g.dashboard.withPanels([
  // ========================================
  // Row 0: Overview Stats (8 panels)
  // Nodes: Total, Problem, Allocated, Idle
  // Jobs: Running, Pending, Failed, Completed
  // ========================================
  statPanelSingle(
    'Total Nodes',
    'count(max by (node) (slurm_node_state{partition=~"$partition"})) or vector(0)',
    {w: 3, h: 4, x: 0, y: 0}
  ),
  statPanelSingle(
    'Problem Nodes',
    'count(max by (node) (slurm_node_state{partition=~"$partition", state=~"DOWN.*|DRAIN.*|FAIL.*|NOT_RESPONDING.*"})) or vector(0)',
    {w: 3, h: 4, x: 3, y: 0}
  ),
  statPanelSingle(
    'Allocated Nodes',
    'count(max by (node) (slurm_node_state{partition=~"$partition", state=~"ALLOCATED|MIXED"})) or vector(0)',
    {w: 3, h: 4, x: 6, y: 0}
  ),
  statPanelSingle(
    'Idle Nodes',
    'count(max by (node) (slurm_node_state{partition=~"$partition", state="IDLE"})) or vector(0)',
    {w: 3, h: 4, x: 9, y: 0}
  ),
  statPanelSingle(
    'Running Jobs',
    'sum(slurm_jobs_running{cluster_name=~"$cluster_name"})',
    {w: 3, h: 4, x: 12, y: 0}
  ),
  statPanelSingle(
    'Pending Jobs',
    'sum(slurm_jobs_pending{cluster_name=~"$cluster_name"})',
    {w: 3, h: 4, x: 15, y: 0}
  ),
  statPanelSingle(
    'Failed Jobs',
    'sum(slurm_jobs_total{cluster_name=~"$cluster_name", state="FAILED"}) or vector(0)',
    {w: 3, h: 4, x: 18, y: 0}
  ),
  statPanelSingle(
    'Completed Jobs',
    'sum(slurm_jobs_total{cluster_name=~"$cluster_name", state="COMPLETED"}) or vector(0)',
    {w: 3, h: 4, x: 21, y: 0}
  ),

  // ========================================
  // Row 1: Nodes by State (unique nodes by selected partition)
  // ========================================
  timeseriesPanel(
    'Nodes by State',
    'sum by (state) (max by (node, state) (slurm_node_state{partition=~"$partition"}))',
    '{{ state }}',
    'none',
    {w: 24, h: 8, x: 0, y: 4}
  ),

  // ========================================
  // Row 2: Problem Nodes drill-down tables
  // ========================================
  tablePanelPrometheus(
    'Problem Nodes - Click Node for Host Metrics',
    'max by (node, state, gpus, cpus, mem, load_alloc, load_total) (slurm_node_state{cluster_name=~"$cluster_name", partition=~"$partition", state=~"DOWN.*|DRAIN.*|FAIL.*|NOT_RESPONDING.*"})',
    {w: 12, h: 6, x: 0, y: 12},
    columns=[
      { name: 'Node', width: 120, link: { title: 'Host Metrics', url: '/d/host-metrics-single/host-metrics?var-hostname=${__value.text}&${__url_time_range}' } },
      { name: 'State', width: 120 },
      { name: 'GPUs', width: 60 },
      { name: 'CPUs', width: 60 },
      { name: 'Memory', width: 80 },
    ]
  ),
  tablePanelPrometheus(
    'Problem GPU Nodes - Click Node for GPU Health',
    'max by (node, state, vendor, gpus, cpus, mem, load_alloc, load_total) (slurm_node_state{cluster_name=~"$cluster_name", partition=~"$partition", state=~"DOWN.*|DRAIN.*|FAIL.*|NOT_RESPONDING.*", gpus!="0", vendor=~"amd|nvidia"})',
    {w: 12, h: 6, x: 12, y: 12},
    columns=[
      { name: 'Node', width: 120, link: { title: 'GPU Health', url: '/d/${__data.fields.Vendor}-gpu-health/gpu-health-status?var-hostname=${__value.text}&${__url_time_range}' } },
      { name: 'State', width: 120 },
      { name: 'Vendor', width: 80 },
      { name: 'GPUs', width: 60 },
      { name: 'CPUs', width: 60 },
      { name: 'Memory', width: 80 },
    ]
  ),

  // ========================================
  // Row 3: Nodes by Reservation
  // ========================================
  timeseriesPanel(
    'Nodes in Reservation',
    'slurm_active_reservations_nodes_total{reservation=~"$reservation"}',
    '{{ reservation }}',
    'none',
    {w: 12, h: 8, x: 0, y: 18}
  ),
  timeseriesPanel(
    'Idle Nodes in Reservation',
    'slurm_reservation_idle_nodes_total{reservation=~"$reservation"}',
    '{{ reservation }}',
    'none',
    {w: 12, h: 8, x: 12, y: 18}
  ),

  // ========================================
  // Row 4: Nodes by Account (Account L1)
  // ========================================
  timeseriesPanel(
    'Allocated Nodes by Account',
    'sum by (account_l1) (slurm_account_nodes{cluster_name=~"$cluster_name", account_l1=~"$account_l1"})',
    '{{ account_l1 }}',
    'none',
    {w: 12, h: 8, x: 0, y: 26}
  ),
  timeseriesPanel(
    'GPUs by Account',
    'sum by (account_l1) (slurm_account_gpus{cluster_name=~"$cluster_name", account_l1=~"$account_l1"})',
    '{{ account_l1 }}',
    'none',
    {w: 12, h: 8, x: 12, y: 26}
  ),

  // ========================================
  // Row 5: Nodes by User
  // ========================================
  timeseriesPanel(
    'Nodes by User',
    'slurm_alloc_nodes_user_count{user=~"$user"}',
    '{{ user }}',
    'none',
    {w: 12, h: 8, x: 0, y: 34}
  ),
  timeseriesPanel(
    'GPUs by User',
    'slurm_alloc_gpus_user_count{user=~"$user"}',
    '{{ user }}',
    'none',
    {w: 12, h: 8, x: 12, y: 34}
  ),
])
