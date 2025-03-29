local g = import './g.libsonnet';
local variables = import './variables.libsonnet';
local row = g.panel.row;

local critical_status_ts = [
{ expr: 'count_values("hostname", oca_version) by(version)', legend_format: '{{version}}', title: 'Hosts with OCA version', unit: 'none' },
{ expr: 'count_values("hostname", gpu_count) by (instance_shape)', legend_format: '{{instance_shape}}', title: 'Shapes with matching GPU count', unit: 'none' },
{ expr: 'count_values("hostname", up{instance=~".*9100"})', legend_format: '{{hostname}}', title: 'Hosts up', unit: 'none' },
{ expr: 'check_bus_issue_count{hostname=~"$hostname", oci_name=~"$oci_name"}', legend_format: '{{ hostname }}', title: 'Devices fallen off bus error count', unit: 'none' },
{ expr: 'DCGM_FI_DEV_XID_ERRORS{Hostname=~"$hostname", gpu=~"$gpu", oci_name=~"$oci_name"}', legend_format: '{{ Hostname }}:{{ gpu }}', title: 'Value of the last XID error encountered', unit: 'none' },
];

local critical_status_stl = [
{ expr1: 'rdma_device_status{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'rdma_device_status{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}:{{rdma_device}}', title: 'RDMA Device Status', unit: 'none', colors: {'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' },} },
{ expr1: 'gpu_row_remap_error_check{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'gpu_row_remap_error_check{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}', title: 'GPU Row Remap Error Check', unit: 'none', colors: {'0': { text: 'passed', color: 'green' },'1': { text: 'failed', color: 'red' },} },
{ expr1: 'gpu_ecc_error_check{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'gpu_ecc_error_check{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}', title: 'GPU ECC Error Check', unit: 'none', colors: {'0': { text: 'failed', color: 'red' },'1': { text: 'passed', color: 'green' },} },
{ expr1: 'xid_error_check{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'xid_error_check{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}', title: 'Xid Error Check', unit: 'none', colors: {'1': { text: 'passed', color: 'green' },'0': { text: 'failed', color: 'red' },} },
];

local health_status = [
{ expr1: 'ib_link_state{hostname=~"$hostname", oci_name=~"$oci_name"}==1 or vector(0)', expr2: 'rdma_device_status{hostname=~"$hostname", oci_name=~"$oci_name"} > 1', legend_format: '{{hostname}}:{{rdma_device}}', title: 'RDMA Link State (h/w metric)', unit: 'none', colors: {'1': { text: 'down', color: 'red' },} },
{ expr1: 'rdma_link_noflap{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'rdma_link_noflap{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}:{{rdma_device}}', title: 'RDMA Link flapping', unit: 'none', colors: {'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' },}  },
{ expr1: 'rttcc_status{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'rttcc_status{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}:{{rdma_device}}', title: 'RTTCC Status', unit: 'none', colors: {'0': { text: 'disabled', color: 'green' },'1': { text: 'enabled', color: 'red' },}  },
{ expr1: 'gpu_count{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'gpu_count{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}:{{instance_shape}}', title: 'GPU Count', unit: 'none', colors: {'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' },}  },
{ expr1: 'oca_version{hostname=~"$hostname", oci_name=~"$oci_name"}==0', expr2: 'oca_version{hostname=~"$hostname", oci_name=~"$oci_name"}==1', legend_format: '{{hostname}}:{{version}}', title: 'OCA Version', unit: 'none', colors: {'0': { text: 'down', color: 'red' },'1': { text: 'up', color: 'green' },}  },
];

local cluster_metrics = [
{ expr: 'avg by (cluster_name) (node_load1{cluster_name=~"$cluster_name"})', legend_format: '1m load average {{cluster_name}}', title: 'Cluster 1m load average', unit: 'percent' },
{ expr: 'avg by (cluster_name) (node_load5{cluster_name=~"$cluster_name"})', legend_format: '5m load average {{cluster_name}}', title: 'Cluster 5m load average', unit: 'percent' },
{ expr: 'avg by (cluster_name) (node_load15{cluster_name=~"$cluster_name"})', legend_format: '15m load average {{cluster_name}}', title: 'Cluster 15m load average', unit: 'percent' },
];

local node_metrics = [
{ expr: '(node_load1{hostname=~"$hostname",oci_name=~"$oci_name"})', legend_format: '{{oci_name}}:{{hostname}}', title: 'Instance 1m load average', unit: 'percent' },
{ expr: '(node_load5{hostname=~"$hostname",oci_name=~"$oci_name"})', legend_format: '{{oci_name}}:{{hostname}}', title: 'Instance 5m load average', unit: 'percent' },
{ expr: '(node_load15{hostname=~"$hostname",oci_name=~"$oci_name"})', legend_format: '{{oci_name}}:{{hostname}}', title: 'Instance 15m load average', unit: 'percent' },
{ expr: 'ceil((1 - (node_memory_MemAvailable_bytes{hostname=~"$hostname",oci_name=~"$oci_name"}/node_memory_MemTotal_bytes{hostname=~"$hostname",oci_name=~"$oci_name"}))*100)', legend_format: '{{oci_name}}:{{hostname}}',  title: 'Memory utilization', unit: 'percent' },
{ expr: 'ceil((1 - (node_filesystem_avail_bytes{hostname=~"$hostname",oci_name=~"$oci_name",mountpoint=~"$mountpoint",device!~"rootfs"} / node_filesystem_size_bytes{hostname=~"$hostname",oci_name=~"$oci_name",mountpoint=~"$mountpoint",device!~"rootfs"}))*100)', legend_format: '{{oci_name}}:{{hostname}}:{{mountpoint}}', title: 'Storage utilization', unit: 'percent'},
{ expr: 'irate(node_disk_reads_completed_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m])', legend_format: '{{oci_name}}:{{hostname}}:{{device}}', title: 'Disk reads completed iops', unit: 'iops'},
{ expr: 'irate(node_disk_writes_completed_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m])', legend_format: '{{oci_name}}:{{hostname}}:{{device}}', title: 'Disk writes completed iops', unit: 'iops'},
{ expr: 'irate(node_disk_read_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m])', legend_format: '{{oci_name}}:{{hostname}}:{{device}}', title: 'Disk read bytes', unit: 'Bps'},
{ expr: 'irate(node_disk_written_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m])', legend_format: '{{oci_name}}:{{hostname}}:{{device}}', title: 'Disk write bytes', unit: 'Bps'},
{ expr: 'irate(node_disk_io_time_seconds_total{hostname=~"$hostname",oci_name=~"$oci_name"}[5m])', legend_format: '{{oci_name}}:{{hostname}}:{{device}}', title: 'Time spent doing I/Os', unit: 'percent'},
{ expr: 'rate(node_network_receive_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device=~"$device"}[5m])', legend_format: "{{oci_name}}:{{hostname}}:{{device}}", title: 'Network Traffic Received', unit: 'Bps'},
{ expr: 'rate(node_network_transmit_bytes_total{hostname=~"$hostname",oci_name=~"$oci_name",device=~"$device"}[5m])', legend_format: "{{oci_name}}:{{hostname}}:{{device}}", title: 'Network Traffic Sent', unit: 'Bps'}
];

local nfs_metrics = [
{ expr: 'rate(node_mountstats_nfs_total_read_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[$__range])', legend_format: '{{oci_name}}:{{hostname}}:{{export}}', title: 'Read Throughput', unit: 'Bps' },
{ expr: 'rate(node_mountstats_nfs_total_write_bytes_total{hostname=~"$hostname", oci_name=~"$oci_name"}[$__range])', legend_format: '{{oci_name}}:{{hostname}}:{{export}}', title: 'Write Throughput', unit: 'Bps' },
{ expr: 'sum by(oci_name, hostname) (rate(node_mountstats_nfs_operations_requests_total{hostname=~"$hostname", oci_name=~"$oci_name", operation!~"READ|WRITE"}[$__range]))', legend_format: '{{oci_name}}:{{hostname}}', title: 'Metadata IOPS', unit: 'iops' },
{ expr: 'sum by(oci_name, hostname) (rate(node_mountstats_nfs_operations_requests_total{hostname=~"$hostname", oci_name=~"$oci_name", operation=~"READ|WRITE"}[$__range]))', legend_format: '{{oci_name}}:{{hostname}}', title: 'Read/Write IOPS', unit: 'iops' },
{ expr: 'sum by(oci_name, hostname, export) (node_nfs_rpc_retransmissions_total{hostname=~"$hostname", oci_name=~"$oci_name"})', legend_format: '{{oci_name}}:{{hostname}}:{{export}}', title: 'NFS Retransmissions', unit: 'cps' },
{ expr: 'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_request_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[$__range]))', legend_format: '{{oci_name}}:{{hostname}}:{{export}}', title: 'NFS Request Time', unit: 's' },
{ expr: 'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_response_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[$__range]))', legend_format: '{{oci_name}}:{{hostname}}:{{export}}', title: 'NFS Response Time', unit: 's' },
{ expr: 'avg by(oci_name, hostname, export) (rate(node_mountstats_nfs_operations_queue_time_seconds_total{hostname=~"$hostname", oci_name=~"$oci_name"}[$__range]))', legend_format: '{{oci_name}}:{{hostname}}:{{export}}', title: 'NFS Queue Time', unit: 's' },
];

local dcgm_metrics = [
  { name: 'DCGM_FI_DEV_SM_CLOCK', title: 'SM Clock', unit: 'hertz' },
  { name: 'DCGM_FI_DEV_MEM_CLOCK', title: 'Memory Clock', unit: 'hertz' },
  { name: 'DCGM_FI_DEV_MEMORY_TEMP', title: 'Memory temperature (in C)', unit: 'celsius'},
  { name: 'DCGM_FI_DEV_GPU_TEMP', title: 'GPU temperature (in C)', unit: 'celsius' },
  { name: 'DCGM_FI_DEV_POWER_USAGE', title: 'Power draw (in W)', unit: 'watts' },
  { name: 'DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION', title: 'Total energy consumption since boot (in mJ)', unit: 'joule' },
  { name: 'DCGM_FI_DEV_PCIE_REPLAY_COUNTER', title: 'Total number of PCIe retries', unit: 'none' },
  { name: 'DCGM_FI_DEV_GPU_UTIL', title: 'GPU Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_MEM_COPY_UTIL', title: 'Memory Copy Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_ENC_UTIL', title: 'Encoder Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_DEC_UTIL', title: 'Decoder Utilization', unit: 'percent' },
  { name: 'DCGM_FI_DEV_FB_FREE', title: 'Framebuffer memory free (in MiB)', unit: 'mbytes' },
  { name: 'DCGM_FI_DEV_FB_USED', title: 'Framebuffer memory used (in MiB)', unit: 'mbytes' },  
  { name: 'DCGM_FI_DEV_NVLINK_BANDWIDTH_TOTAL', title: 'Total number of NVLink bandwidth counters for all lanes', unit: 'none' },
  { name: 'DCGM_FI_PROF_PCIE_TX_BYTES', title: 'PCIe transmitted bytes (in MiB)', unit: 'MiBs' },
  { name: 'DCGM_FI_PROF_PCIE_RX_BYTES', title: 'PCIe received bytes (in MiB)', unit: 'MiBs' },  
];

local dcgm_errors = [
  { name: 'DCGM_FI_DEV_ECC_SBE_VOL_TOTAL', title: 'Total number of single-bit volatile ECC errors', unit: 'cps' },
  { name: 'DCGM_FI_DEV_ECC_DBE_VOL_TOTAL', title: 'Total number of double-bit volatile ECC errors', unit: 'cps' },
  { name: 'DCGM_FI_DEV_ECC_SBE_AGG_TOTAL', title: 'Total number of single-bit persistent ECC errors', unit: 'cps' },
  { name: 'DCGM_FI_DEV_ECC_DBE_AGG_TOTAL', title: 'Total number of double-bit persistent ECC errors', unit: 'cps' },
  { name: 'DCGM_FI_DEV_UNCORRECTABLE_REMAPPED_ROWS', title: 'Number of remapped rows for uncorrectable errors', unit: 'cps' },
  { name: 'DCGM_FI_DEV_CORRECTABLE_REMAPPED_ROWS', title: 'Number of remapped rows for correctable errors', unit: 'cps' },
  { name: 'DCGM_FI_DEV_ROW_REMAP_FAILURE', title: 'Whether remapping of rows has failed', unit: 'cps' },
  { name: 'DCGM_FI_DEV_XID_ERRORS', title: 'Value of the last XID error encountered', unit: 'none' },
];

local nvlink_metrics = [
{ name: 'nvlink_data_tx_kib', title: 'Total data transmitted', unit: 'KBs' },
{ name: 'nvlink_data_rx_kib', title: 'Total data received', unit: 'KBs' },
{ name: 'nvlink_raw_tx_kib', title: 'Total raw bytes transmitted', unit: 'KBs' },
{ name: 'nvlink_raw_rx_kib', title: 'Total raw bytes received', unit: 'KBs' },
];

local ib_port_metrics = [
{ name: 'ib_port_xmit_data', title: 'Total number of data octets transmitted', unit: 'Bps' },
{ name: 'ib_port_rcv_data', title: 'Total number of data octets received', unit: 'Bps' },
{ name: 'ib_port_xmit_packets', title: 'Total number of packets transmitted', unit: 'pps' },
{ name: 'ib_port_rcv_packets', title: 'Total number of packets received', unit: 'pps' },
{ name: 'ib_unicast_rcv_packets', title: 'Total number of unicast packets received', unit: 'pps' },
{ name: 'ib_unicast_xmit_packets', title: 'Total number of unicast packets transmitted', unit: 'pps' },
{ name: 'ib_multicast_rcv_packets', title: 'Total number of multicast packets received', unit: 'pps' },
{ name: 'ib_multicast_xmit_packets', title: 'Total number of multicast packets transmitted', unit: 'pps' },
];

local roce2_errors = [
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

g.dashboard.new('Cluster Dashboard')
+ g.dashboard.withUid('cluster-dashboard')
+ g.dashboard.withDescription(|||
  Dashboard for GPU Clusters
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.availability_domain,
  variables.compartment,
  variables.rack_id,
  variables.rail_id,
  variables.hpc_island,
  variables.cluster,
  variables.oci_name,
  variables.hostname,
  variables.fss_mount,
  variables.mountpoint,
  variables.fstype,
  variables.device,
  variables.interface,
  variables.gpu,
])
+ g.dashboard.withPanels(
  g.util.grid.makeGrid([
    row.new('Critical Status')
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
      for metric in critical_status_ts] +
      [g.panel.stateTimeline.new(metric.title)
        + g.panel.stateTimeline.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr1,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format),
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr2,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format),
        ])
        + g.panel.stateTimeline.standardOptions.withUnit(metric.unit)
        + g.panel.stateTimeline.options.withShowValue('never')
        + g.panel.stateTimeline.gridPos.withW(24)
        + g.panel.stateTimeline.gridPos.withH(8)
        + g.panel.stateTimeline.standardOptions.withMappings(
           g.panel.stateTimeline.standardOptions.mapping.ValueMap.withType() +  
           g.panel.stateTimeline.standardOptions.mapping.ValueMap.withOptions(metric.colors)
          )
      for metric in critical_status_stl]
      ),
    row.new('Health Status')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.stateTimeline.new(metric.title)
        + g.panel.stateTimeline.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr1,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format),
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                metric.expr2,
            )
            + g.query.prometheus.withLegendFormat(metric.legend_format),
        ])
        + g.panel.stateTimeline.standardOptions.withUnit(metric.unit)
        + g.panel.stateTimeline.options.withShowValue('never')
        + g.panel.stateTimeline.gridPos.withW(24)
        + g.panel.stateTimeline.gridPos.withH(8)
        + g.panel.stateTimeline.standardOptions.withMappings(
           g.panel.stateTimeline.standardOptions.mapping.ValueMap.withType() +  
           g.panel.stateTimeline.standardOptions.mapping.ValueMap.withOptions(metric.colors)
          )
      for metric in health_status
      ]),
    row.new('Cluster Metrics')
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
    row.new('Node Metrics')
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
    row.new('NFS Metrics')
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
      for metric in nfs_metrics
      ]),
    row.new('GPU Metrics')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                'avg by(Hostname, gpu) (' + metric.name + '{Hostname=~"$hostname", oci_name=~"$oci_name"})',
            )
            + g.query.prometheus.withLegendFormat('{{ Hostname }}:{{ gpu }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in dcgm_metrics
      ]),
    row.new('GPU Errors')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                'avg by(Hostname, gpu) (' + metric.name + '{Hostname=~"$hostname", oci_name=~"$oci_name"})',
            )
            + g.query.prometheus.withLegendFormat('{{ Hostname }}:{{ gpu }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in dcgm_errors
      ]),
    row.new('NVLink Metrics')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                'irate(' + metric.name + '{hostname=~"$hostname",oci_name=~"$oci_name", gpu=~"$gpu"}[5m])',
            )
            + g.query.prometheus.withLegendFormat('{{ hostname }}:{{ oci_name }}:{{ gpu }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in nvlink_metrics      
      ]),
    row.new('ROCEv2 Port Metrics')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                'irate(' + metric.name + '{hostname=~"$hostname", oci_name=~"$oci_name", interface=~"$interface"}[5m])',
            )
            + g.query.prometheus.withLegendFormat('{{oci_name}}:{{ hostname }}:{{ interface }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in ib_port_metrics
      ]),
    row.new('ROCEv2 Congestion Metrics')
    + row.withCollapsed(true)
    + row.withPanels([
      g.panel.timeSeries.new(metric.title)
        + g.panel.timeSeries.queryOptions.withTargets([
            g.query.prometheus.new(
                '$PROMETHEUS_DS',
                '(' + metric.name + '{hostname=~"$hostname", oci_name=~"$oci_name", interface=~"$interface"})',
            )
            + g.query.prometheus.withLegendFormat('{{oci_name}}:{{ hostname }}:{{ interface }}')
        ])
        + g.panel.timeSeries.standardOptions.withUnit(metric.unit)
        + g.panel.timeSeries.gridPos.withW(24)
        + g.panel.timeSeries.gridPos.withH(8)
      for metric in roce2_errors
      ]),    
  ])  
)
