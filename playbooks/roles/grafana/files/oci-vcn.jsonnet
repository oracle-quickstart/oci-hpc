local g = import './g.libsonnet';
local variables = import './oci-vcn-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

g.dashboard.new('Virtual Cloud Network')
+ g.dashboard.withUid('oci-vcn')
+ g.dashboard.withDescription(|||
  OCI VCN Metrics
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('30s')
+ g.dashboard.time.withFrom('now-5m')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.hostname,
  variables.oci_name,
  variables.cluster_name,
])

+ g.dashboard.withPanels([
    timeseriesPanel(
      'VNIC Ingress Top 10',
      'topk(10, rate(oci_vcn:vnic_from_network_bytes_count[5m]))',
      '{{hostname}}:{{display_name}}',
      'Bps',
      {w:12, h:8, x:0, y:0}
    ),    
    timeseriesPanel(
      'VNIC Egress Top 10',
      'topk(10, rate(oci_vcn:vnic_to_network_bytes_count[5m]))',
      '{{hostname}}:{{display_name}}',
      'Bps',
      {w:12, h:8, x:12, y:0}
    ),    
    timeseriesPanel(
      'VNIC Ingress Drops',
      'topk(10, rate(oci_vcn:vnic_ingress_drops_throttle_count[5m]))',
      '{{hostname}}:{{display_name}}',
      'pps',
      {w:12, h:8, x:0, y:8}
    ),    
    timeseriesPanel(
      'VNIC Egress Drops',
      'topk(10, rate(oci_vcn:vnic_egress_drops_throttle_count[5m]))',
      '{{hostname}}:{{display_name}}',
      'pps',
      {w:12, h:8, x:12, y:8}
    ),    
    timeseriesPanel(
      'VNIC ConnTrack Util',
      'topk(10, rate(oci_vcn:vnic_conntrack_util_percent_count[5m]))',
      '{{hostname}}:{{display_name}}',
      'percent',
      {w:12, h:8, x:0, y:16}
    ),    
    timeseriesPanel(
      'VNIC ConnTrack Is Full',
      'topk(10, rate(oci_vcn:vnic_conntrack_is_full_count[5m]))',
      '{{hostname}}:{{display_name}}',
      'none',
      {w:12, h:8, x:12, y:16}
    ),    
])

