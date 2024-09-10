local g = import './g.libsonnet';
local variables = import './variables.libsonnet';
local row = g.panel.row;

local dcgm_metrics = [
  { name: 'DCGM_FI_DEV_SM_CLOCK', title: 'SM Clock', unit: 'hertz' },
  { name: 'DCGM_FI_DEV_MEM_CLOCK', title: 'Memory Clock', unit: 'hertz' },
  { name: 'DCGM_FI_DEV_MEMORY_TEMP', title: 'Memory temperature (in C)', unit: 'celsius'},
  { name: 'DCGM_FI_DEV_GPU_TEMP', title: 'GPU temperature (in C)', unit: 'celsius' },
  { name: 'DCGM_FI_DEV_POWER_USAGE', title: 'Power draw (in W)', unit: 'watts' },
  { name: 'DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION', title: 'Total energy consumption since boot (in mJ)', unit: 'joules' },
  { name: 'DCGM_FI_DEV_PCIE_REPLAY_COUNTER', title: 'Total number of PCIe retries', unit: 'none' },
  { name: 'DCGM_FI_DEV_GPU_UTIL', title: 'GPU Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_MEM_COPY_UTIL', title: 'Memory Copy Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_ENC_UTIL', title: 'Encoder Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_DEC_UTIL', title: 'Decoder Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_XID_ERRORS', title: 'Value of the last XID error encountered', unit: 'none' },
  { name: 'DCGM_FI_DEV_FB_FREE', title: 'Framebuffer memory free (in MiB)', unit: 'megabytes' },
  { name: 'DCGM_FI_DEV_FB_USED', title: 'Framebuffer memory used (in MiB)', unit: 'megabytes' },  
  { name: 'DCGM_FI_DEV_VGPU_LICENSE_STATUS', title: 'vGPU License status', unit: 'none' },
  { name: 'DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL', title: 'Total number of NVLink bandwidth counters for all lanes', unit: 'none' },
  { name: 'DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS', title: 'Number of remapped rows for uncorrectable errors', unit: 'none' },
  { name: 'DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS', title: 'Number of remapped rows for correctable errors', unit: 'none' },
  { name: 'DCGM_FI_DEV_ROW_REMAP_FAILURE', title: 'Whether remapping of rows has failed', unit: 'none' },
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

local cluster_metrics = [
{ expr: 'avg by (cluster_name) (node_load1)', legend_format: '1m load average {{cluster_name}}', title: 'Cluster 1m load average', unit: 'percent' },
{ expr: 'avg by (cluster_name) (node_load5)', legend_format: '5m load average {{cluster_name}}', title: 'Cluster 5m load average', unit: 'percent' },
{ expr: 'avg by (cluster_name) (node_load15)', legend_format: '15m load average {{cluster_name}}', title: 'Cluster 15m load average', unit: 'percent' },
];

local node_metrics = [
{ expr: '(node_load1{oci_name=~"$oci_name"})', legend_format: '{{oci_name}}', title: 'Instance 1m load average', unit: 'percent' },
{ expr: '(node_load5{oci_name=~"$oci_name"})', legend_format: '{{oci_name}}', title: 'Instance 5m load average', unit: 'percent' },
{ expr: '(node_load15{oci_name=~"$oci_name"})', legend_format: '{{oci_name}}', title: 'Instance 15m load average', unit: 'percent' },
{ expr: 'ceil((1 - (node_memory_MemAvailable_bytes{oci_name=~"$oci_name"}/node_memory_MemTotal_bytes{oci_name=~"$oci_name"}))*100)', legend_format: '{{oci_name}}',  title: 'Memory utilization', unit: 'percent' },
{ expr: 'ceil((1 - (node_filesystem_avail_bytes{mountpoint=~"$mountpoint",device!~"rootfs"} / node_filesystem_size_bytes{mountpoint=~"$mountpoint",device!~"rootfs"}))*100)', legend_format: '{{mountpoint}}', title: 'Storage utilization', unit: 'percent'},
{ expr: 'rate(node_network_receive_bytes_total{oci_name=~"$oci_name",device=~"$device"}[$__rate_interval])', legend_format: "{{oci_name}} {{device}}", title: 'Network Traffic Received', unit: 'bytes'},
{ expr: 'rate(node_network_transmit_bytes_total{oci_name=~"$oci_name",device=~"$device"}[$__rate_interval])', legend_format: "{{oci_name}} {{device}}", title: 'Network Traffic Sent', unit: 'bytes'}
];

g.dashboard.new('Cluster Dashboard')
+ g.dashboard.withUid('cluster-dashboard')
+ g.dashboard.withDescription(|||
  Dashboard for GPU Clusters
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster,
  variables.oci_name,
  variables.mountpoint,
  variables.fstype,
  variables.device,
  variables.interface,
  variables.gpu,
])
+ g.dashboard.withPanels(
  g.util.grid.makeGrid([
    row.new('Cluster')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format)
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in cluster_metrics
      ]),
    row.new('Node')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format)
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in node_metrics
      ]),
    row.new('GPU')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                'avg by(Hostname) (' + metric.name + '{Hostname=~"$oci_name"})',
            )
            + g.query.prometheus.withLegendFormat('Host {{ Hostname }}')
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
                '$PROMETHEUS_DS',
                '(' + metric.name + '{hostname=~"$oci_name",interface=~"$interface"})',
            )
            + g.query.prometheus.withLegendFormat('RDMA hardware counters by host {{ oci_name }} and nic {{ interface }}')
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
                '$PROMETHEUS_DS',
                'sum by(gpu) (' + metric.name + '{hostname=~"$oci_name",gpu=~"$gpu"})',
            )
            + g.query.prometheus.withLegendFormat('Total NVLink bandwidth usage by host {{ oci_name }} and gpu {{ gpu }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in nvlink_metrics      
      ]),
  ])  
)

