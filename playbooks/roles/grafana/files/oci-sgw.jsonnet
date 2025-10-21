local g = import './g.libsonnet';
local variables = import './oci-sgw-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('Service Gateway')
+ g.dashboard.withUid('oci-sgw')
+ g.dashboard.withDescription(|||
  Service Gateway
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-5m')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.cluster_name,
])

+ g.dashboard.withPanels([
    timeseriesPanel(
      'Bytes From Service',
      'rate(oci_service_gateway:bytes_from_service_count[5m])',
      '{{cluster_name}}',
      'Bps',
      {w:12, h:8, x:0, y:0}
    ),    
    timeseriesPanel(
      'Bytes To Service',
      'rate(oci_service_gateway:bytes_to_service_count[5m])',
      '{{cluster_name}}',
      'Bps',
      {w:12, h:8, x:12, y:0}
    ),    
    timeseriesPanel(
      'Packets From Service',
      'rate(oci_service_gateway:packets_from_service_count[5m])',
      '{{cluster_name}}',
      'pps',
      {w:12, h:8, x:0, y:8}
    ),    
    timeseriesPanel(
      'Packets To Service',
      'rate(oci_service_gateway:packets_to_service_count[5m])',
      '{{cluster_name}}',
      'pps',
      {w:12, h:8, x:12, y:8}
    ),    
    timeseriesPanel(
      'Drops From Service',
      'rate(oci_service_gateway:sgw_drops_from_service_count[5m])',
      '{{cluster_name}}',
      'none',
      {w:12, h:8, x:0, y:16}
    ),    
    timeseriesPanel(
      'Drops To Service',
      'rate(oci_service_gateway:sgw_drops_to_service_count[5m])',
      '{{drop_type}}',
      'none',
      {w:12, h:8, x:12, y:16}
    ),    
])

