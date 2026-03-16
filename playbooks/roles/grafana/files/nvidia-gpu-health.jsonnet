local g = import './g.libsonnet';
local variables = import './nvidia-gpu-metrics-single-variables.libsonnet';
local stateTimeline = import './statetimeline-panel.libsonnet';
local statHealth = import './stat-health-panel.libsonnet';
local row = g.panel.row;
g.dashboard.new('NVIDIA GPU Health')
+ g.dashboard.withUid('nvidia-gpu-health')
+ g.dashboard.withDescription(|||
  GPU Node Component Health Status
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-5m')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname
])
+ g.dashboard.withPanels([
   statHealth(
      'RTTCC',
      'node_rttcc_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:0, y:0}
   ),
   statHealth(
      'OCA Ver',
      'node_oca_ver_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:3, y:0}
   ),
   statHealth(
      'RDMA Dev',
      'node_rdma_device_status_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:6, y:0}
   ),
   statHealth(
      'Bus Issue',
      'node_check_bus_issue_count_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:9, y:0}
   ),
   statHealth(
      'Link Flap',
      'node_rdma_link_flapping_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:12, y:0}
   ),
   statHealth(
      'ECC SBE',
      'node_ecc_sbe_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:15, y:0}
   ),
   statHealth(
      'ECC DBE',
      'node_ecc_dbe_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:18, y:0}
   ),
   statHealth(
      'Row Remap Pending',
      'node_row_remap_pending_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:21, y:0}
   ),
   statHealth(
      'Row Remap Failed',
      'node_row_remap_failure_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:0, y:3}
   ),
   statHealth(
      'Xid',
      'node_xid_severity_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:3, y:3}
   ),
   statHealth(
      'Power Violation',
      'node_gpu_power_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:6, y:3}
   ),
   statHealth(
      'Board Limit Violation',
      'node_gpu_board_limit_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:9, y:3}
   ),
   statHealth(
      'Thermal Violation',
      'node_gpu_thermal_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:12, y:3}
   ),
   statHealth(
      'Sync Boost Violation',
      'node_gpu_sync_boost_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:15, y:3}
   ),
   statHealth(
      'Reliability Violation',
      'node_gpu_reliability_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:18, y:3}
   ),
   statHealth(
      'PCIE Correctable',
      'node_pcie_aer_correctable_errors_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:21, y:3}
   ),
   statHealth(
      'PCIE Non Fatal',
      'node_pcie_aer_nonfatal_errors_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:0, y:6}
   ),
   statHealth(
      'PCIE Fatal',
      'node_pcie_aer_fatal_errors_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:3, y:6}
   ),
   statHealth(
      'PCIE Bus Inaccessible',
      'node_pcie_bus_inaccessible_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:6, y:6}
   ),
   statHealth(
      'PCIE Link Width',
      'node_pcie_bus_linkwidth_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:9, y:6}
   ),
   statHealth(
      'Disk free',
      'node_disk_free_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:12, y:6}
   ),
   statHealth(
      'Mem free',
      'node_memory_availability_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:15, y:6}
   ),
   statHealth(
      'GPU Count',
      'node_gpu_count_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:18, y:6}
   ),
   statHealth(
      'GPU Health',
      'node_nvidia_gpu_health_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:21, y:6}
   ),  
   statHealth(
      'GPU PCIE',
      'node_nvidia_gpu_health_pcie_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:0, y:6}
   ),
   statHealth(
      'GPU NVLink',
      'node_nvidia_gpu_health_nvlink_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:3, y:6}
   ),
   statHealth(
      'GPU PMU',
      'node_nvidia_gpu_health_pmu_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:6, y:6}
   ),
   statHealth(
      'GPU MCU',
      'node_nvidia_gpu_health_mcu_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:9, y:6}
   ),
   statHealth(
      'GPU MEM',
      'node_nvidia_gpu_health_mem_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:12, y:6}
   ),
   statHealth(
      'GPU SM',
      'node_nvidia_gpu_health_sm_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:15, y:6}
   ),
   statHealth(
      'GPU Power',
      'node_nvidia_gpu_health_power_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:18, y:6}
   ),
   statHealth(
      'GPU Thermal',
      'node_nvidia_gpu_health_thermal_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:21, y:6}
   ),   
   stateTimeline(
    'PCIE Health Score history',
    'sum by (hostname, device) (increase(pcie_aer_correctable_error_count{hostname=~"$hostname"}[5m]) + increase(pcie_aer_nonfatal_error_count{hostname=~"$hostname"}[5m]) * 10 + increase(pcie_aer_fatal_error_count{hostname=~"$hostname"}[5m]) * 100)',
    '{{ device }}',
    {w:24, h:12, x:0, y:9},
    {'0': { text: 'ok', color: 'green' },'10': { text: 'warning', color: 'yellow'}, '100': { text: 'error', color: 'red'}}
   ),
   stateTimeline(
    'RDMA Link Flapping history',
    'rdma_link_noflap{hostname=~"$hostname"}',
    '{{ rdma_device }}',
    {w:24, h:10, x:0, y:21}
   )
])
