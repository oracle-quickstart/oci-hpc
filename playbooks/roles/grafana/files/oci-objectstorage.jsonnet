local g = import './g.libsonnet';
local variables = import './oci-objectstorage-variables.libsonnet';
local timeseriesPanel = import './timeseries-panel.libsonnet';

local bucketFilter = 'display_name=~"$bucket"';
local capacityFilter = bucketFilter + ',tier=~"$tier"';

g.dashboard.new('OCI Object Storage')
+ g.dashboard.withUid('oci-objectstorage')
+ g.dashboard.withDescription(|||
  OCI Object Storage capacity, request volume, client errors, and latency.
|||)
+ g.dashboard.withTimezone('browser')
+ g.dashboard.withRefresh('1m')
+ g.dashboard.time.withFrom('now-24h')
+ g.dashboard.graphTooltip.withSharedCrosshair()
+ g.dashboard.withVariables([
  variables.prometheus,
  variables.bucket,
  variables.tier,
])
+ g.dashboard.withPanels([
  timeseriesPanel(
    'Request Rate by Bucket',
    'sum by (display_name) (oci_objectstorage:all_requests_count{' + bucketFilter + '}) / 60',
    '{{display_name}}',
    'reqps',
    { w: 12, h: 8, x: 0, y: 0 },
  ),
  timeseriesPanel(
    'Request Operations',
    [
      'sum by (display_name) (oci_objectstorage:get_requests_count{' + bucketFilter + '}) / 60',
      'sum by (display_name) (oci_objectstorage:put_requests_count{' + bucketFilter + '}) / 60',
      'sum by (display_name) (oci_objectstorage:list_requests_count{' + bucketFilter + '}) / 60',
      'sum by (display_name) (oci_objectstorage:delete_requests_count{' + bucketFilter + '}) / 60',
    ],
    [
      'GET {{display_name}}',
      'PUT {{display_name}}',
      'LIST {{display_name}}',
      'DELETE {{display_name}}',
    ],
    'reqps',
    { w: 12, h: 8, x: 12, y: 0 },
  ),

  timeseriesPanel(
    'Client Errors by Bucket',
    'sum by (display_name) (oci_objectstorage:client_errors_count{' + bucketFilter + '})',
    '{{display_name}}',
    'none',
    { w: 12, h: 8, x: 0, y: 8 },
  ),
  timeseriesPanel(
    'Client Error Rate by Bucket',
    '100 * sum by (display_name) (oci_objectstorage:client_errors_count{' + bucketFilter + '}) / clamp_min(sum by (display_name) (oci_objectstorage:all_requests_count{' + bucketFilter + '}), 1)',
    '{{display_name}}',
    'percent',
    { w: 12, h: 8, x: 12, y: 8 },
  ),

  timeseriesPanel(
    'Mean First Byte Latency',
    'avg by (display_name) (oci_objectstorage:first_byte_latency_count{' + bucketFilter + '})',
    '{{display_name}}',
    'ms',
    { w: 12, h: 8, x: 0, y: 16 },
  ),
  timeseriesPanel(
    'Mean Total Request Latency',
    'avg by (display_name) (oci_objectstorage:total_request_latency_count{' + bucketFilter + '})',
    '{{display_name}}',
    'ms',
    { w: 12, h: 8, x: 12, y: 16 },
  ),

  timeseriesPanel(
    'Stored Bytes by Bucket and Tier',
    'sum by (display_name, tier) (last_over_time(oci_objectstorage:stored_bytes_count{' + capacityFilter + '}[3h]))',
    '{{display_name}} / {{tier}}',
    'bytes',
    { w: 12, h: 8, x: 0, y: 24 },
  ),
  timeseriesPanel(
    'Object Count by Bucket and Tier',
    'sum by (display_name, tier) (last_over_time(oci_objectstorage:object_count_count{' + capacityFilter + '}[3h]))',
    '{{display_name}} / {{tier}}',
    'none',
    { w: 12, h: 8, x: 12, y: 24 },
  ),

  timeseriesPanel(
    'Average Object Size',
    'sum by (display_name) (last_over_time(oci_objectstorage:stored_bytes_count{' + capacityFilter + '}[3h])) / clamp_min(sum by (display_name) (last_over_time(oci_objectstorage:object_count_count{' + capacityFilter + '}[3h])), 1)',
    '{{display_name}}',
    'bytes',
    { w: 12, h: 8, x: 0, y: 32 },
  ),
  timeseriesPanel(
    'Uncommitted Multipart Uploads',
    'sum by (display_name, tier) (last_over_time(oci_objectstorage:uncommitted_parts_count{' + capacityFilter + '}[3h]))',
    '{{display_name}} / {{tier}}',
    'bytes',
    { w: 12, h: 8, x: 12, y: 32 },
  ),
])
