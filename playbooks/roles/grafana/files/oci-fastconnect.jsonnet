local g = import './g.libsonnet';
local variables = import './oci-fastconnect-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('Fast Connect')
+ g.dashboard.withUid('oci-fastconnet')
+ g.dashboard.withDescription(|||
  Fast Connect
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
      'Bits Received',
      'rate(oci_fastconnect:bits_received_count[5m])',
      '{{cluster_name}}',
      'Bps',
      {w:12, h:8, x:0, y:0}
    ),    
    timeseriesPanel(
      'Bits Sent',
      'rate(oci_fastconnect:bits_sent_count[5m])',
      '{{cluster_name}}',
      'Bps',
      {w:12, h:8, x:12, y:0}
    ),    
    timeseriesPanel(
      'Packets Received',
      'rate(oci_fastconnect:packets_received_count[5m])',
      '{{cluster_name}}',
      'pps',
      {w:12, h:8, x:0, y:8}
    ),    
    timeseriesPanel(
      'Packets Sent',
      'rate(oci_fastconnect:packets_sent_count[5m])',
      '{{cluster_name}}',
      'pps',
      {w:12, h:8, x:12, y:8}
    ),    
    timeseriesPanel(
      'Packets Discarded',
      'rate(oci_fastconnect:packets_discarded_count[5m])',
      '{{cluster_name}}',
      'none',
      {w:12, h:8, x:0, y:16}
    ),    
    timeseriesPanel(
      'Packets Error',
      'rate(oci_fastconnect:packets_error_count[5m])',
      '{{cluster_name}}',
      'none',
      {w:12, h:8, x:12, y:16}
    ),    
    timeseriesPanel(
      'Connection State',
      'rate(oci_fastconnect:connection_state_count[5m])',
      '{{cluster_name}}',
      'none',
      {w:12, h:8, x:12, y:24}
    ),     
])

