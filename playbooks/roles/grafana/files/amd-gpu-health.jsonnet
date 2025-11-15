local g = import './g.libsonnet';
local variables = import './amd-gpu-metrics-single-variables.libsonnet';
local stateTimeline = import './statetimeline-panel.libsonnet';
local statHealth = import './stat-health-panel.libsonnet';
local row = g.panel.row;
g.dashboard.new('AMD GPU Health')
+ g.dashboard.withUid('amd-gpu-health')
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
      'Link Flap',
      'node_rdma_link_flapping_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:9, y:0}
   ),
   statHealth(
      'ECC Corr',
      'node_amd_ecc_correctable_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:12, y:0}
   ),
   statHealth(
      'ECC Un Corr',
      'node_amd_ecc_uncorrectable_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:15, y:0}
   ),
   statHealth(
      'Power Violation',
      'node_amd_gpu_power_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:18, y:0}
   ),
   statHealth(
      'Thermal Violation',
      'node_amd_gpu_thermal_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:21, y:0}
   ),
   statHealth(
      'HBM Thermal Violation',
      'node_amd_gpu_hbm_thermal_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:0, y:3}
   ),
   statHealth(
      'Proc Hot Violation',
      'node_amd_gpu_processor_hot_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:3, y:3}
   ),
   statHealth(
      'VR Thermal Violation',
      'node_amd_gpu_vr_thermal_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:6, y:3}
   ),
   statHealth(
      'Current Violation',
      'node_amd_gpu_current_violation_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:9, y:3}
   ),
   statHealth(
      'PCIE Correctable',
      'node_pcie_aer_correctable_errors_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:12, y:3}
   ),
   statHealth(
      'PCIE Non Fatal',
      'node_pcie_aer_nonfatal_errors_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:15, y:3}
   ),
   statHealth(
      'PCIE Fatal',
      'node_pcie_aer_fatal_errors_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:18, y:3}
   ),
   statHealth(
      'PCIE Bus Inaccessible',
      'node_pcie_bus_inaccessible_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:21, y:3}
   ),
   statHealth(
      'AMD PCIE Link Width',
      'node_amd_pcie_link_width_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:0, y:6}
   ),
   statHealth(
      'AMD PCIE Link Speed',
      'node_amd_pcie_link_width_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:3, y:6}
   ),
   statHealth(
      'AMD PCIE Replay',
      'node_amd_pcie_replay_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:6, y:6}
   ),
   statHealth(
      'AMD PCIE Nack',
      'node_amd_pcie_nack_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:9, y:6}
   ),
   statHealth(
      'AMD PCIE Recovery',
      'node_amd_pcie_recovery_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:12, y:6}
   ),
   statHealth(
      'Disk free',
      'node_disk_free_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:15, y:6}
   ),
   statHealth(
      'Mem free',
      'node_memory_availability_ok{hostname=~"$hostname"}',
      {w:3, h:3, x:18, y:6}
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
