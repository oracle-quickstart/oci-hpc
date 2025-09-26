local g = import './g.libsonnet';
local variables = import './oci-natgw-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('NAT Gateway')
+ g.dashboard.withUid('oci-natgw')
+ g.dashboard.withDescription(|||
  NAT Gateway
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
      'Bytes From NAT Gateway',
      'rate(oci_nat_gateway:bytes_from_natgw_count[5m])',
      '{{cluster_name}}',
      'Bps',
      {w:12, h:8, x:0, y:0}
    ),    
    timeseriesPanel(
      'Bytes To NAT Gateway',
      'rate(oci_nat_gateway:bytes_to_natgw_count[5m])',
      '{{cluster_name}}',
      'Bps',
      {w:12, h:8, x:12, y:0}
    ),    
    timeseriesPanel(
      'Packets From NAT Gateway',
      'rate(oci_nat_gateway:packets_from_natgw_count[5m])',
      '{{cluster_name}}',
      'pps',
      {w:12, h:8, x:0, y:8}
    ),    
    timeseriesPanel(
      'Packets To NAT Gateway',
      'rate(oci_nat_gateway:packets_to_natgw_count[5m])',
      '{{cluster_name}}',
      'pps',
      {w:12, h:8, x:12, y:8}
    ),       
    timeseriesPanel(
      'Drops To NAT Gateway',
      'rate(oci_nat_gateway:drops_to_natgw_count[5m])',
      '{{drop_type}}',
      'none',
      {w:12, h:8, x:12, y:16}
    ),    
])

