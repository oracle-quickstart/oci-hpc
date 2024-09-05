local g = import './g.libsonnet';
local variables = import './variables.libsonnet';
local row = g.panel.row;

local dcgm_metrics = [
  { name: 'DCGM_FI_DEV_GPU_UTIL', title: 'GPU Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_SM_CLOCK', title: 'SM Clock', unit: 'hertz' },
  { name: 'DCGM_FI_DEV_MEM_CLOCK', title: 'Memory Clock', unit: 'hertz' },
  { name: 'DCGM_FI_DEV_FB_USED', title: 'Frame Buffer Used', unit: 'bytes' },
  { name: 'DCGM_FI_DEV_MEM_COPY_UTIL', title: 'Memory Copy Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_POWER_USAGE', title: 'Power Usage', unit: 'watt' },
  { name: 'DCGM_FI_DEV_ENC_UTIL', title: 'Encoder Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_DEC_UTIL', title: 'Decoder Utilization', unit: 'percent' },
];

local rdma_metrics = [
{ name: 'rdma_np_ecn_marked_roce_packets', title: 'Number of ROCEv2 packets marked for congestion', unit: 'none' },
{ name: 'rdma_out_of_sequence', title: 'Number of out of sequence packets received', unit: 'none' },
{ name: 'rdma_packet_seq_err', title: 'Number of received NAK sequence error packets', unit: 'none' },
{ name: 'rdma_local_ack_timeout_err', title: 'Number of times QPs ack timer expired', unit: 'none' },
{ name: 'rdma_roce_adp_retrans', title: 'Number of adaptive retransmissions for RoCE traffic', unit: 'none' },
{ name: 'rdma_np_cnp_sent', title: 'Number of CNP packets sent', unit: 'none' },
{ name: 'rdma_rp_cnp_handled', title: 'Number of CNP packets handled to throttle', unit: 'none' },
{ name: 'rdma_rp_cnp_ignored', title: 'Number of CNP packets received and ignored', unit: 'none' },
{ name: 'rdma_rx_icrc_encapsulated', title: 'Number of RoCE packets with ICRC (Invertible Cyclic Redundancy Check) errors', unit: 'none' },
{ name: 'rdma_roce_slow_restart', title: 'Number of times RoCE slow restart was used', unit: 'none' },
];

local nvlink_metrics = [
{ name: 'nvlink_data_tx_kib', title: 'Total data in KiB transmitted', unit: 'KB' },
{ name: 'nvlink_data_rx_kib', title: 'Total data in KiB received', unit: 'KB' },
{ name: 'nvlink_raw_tx_kib', title: 'Total raw bytes in KiB transmitted', unit: 'KB' },
{ name: 'nvlink_raw_rx_kib', title: 'Total raw bytes in KiB received', unit: 'KB' },
];

g.dashboard.new('GPU RDMA NVLink Dashboard')
+ g.dashboard.withUid('cluster-dashboard')
+ g.dashboard.withDescription(|||
  Dashboard - covers host, GPU, RDMA and NVLink metrics
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.datasource,
  variables.hostname,
])
+ g.dashboard.withPanels(
  g.util.grid.makeGrid([
    row.new('GPU')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                'Prometheus',
                'avg by(Hostname) (' + metric.name + ')',
            )
            + g.query.prometheus.withLegendFormat('{{ Hostname }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in dcgm_metrics
      ]),
    row.new('RDMA')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                'Prometheus',
                '(' + metric.name + ')',
            )
            + g.query.prometheus.withLegendFormat('{{ interface }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in rdma_metrics
      ]),    
    row.new('NVLink')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                'Prometheus',
                'sum by(gpu) (' + metric.name + ')',
            )
            + g.query.prometheus.withLegendFormat('{{ gpu }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in nvlink_metrics      
      ]),
  ])  
)

