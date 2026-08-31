locals {
  existing_dynamic_group_id   = try(coalesce(var.dynamic_group_id), null)
  should_create_dynamic_group = var.create_policies && !var.use_existing_dynamic_group && local.existing_dynamic_group_id == null
  lookup_default_identity_domain = (
    var.create_policies && var.use_default_identity_domain
  )
  principal_matching_rule = format(
    "ANY {instance.compartment.id = '%s', resource.compartment.id = '%s'}",
    var.targetCompartment,
    var.targetCompartment
  )
  network_compartment_id = var.vcn_compartment != "" ? var.vcn_compartment : var.targetCompartment
  separate_network_policy = (
    local.network_compartment_id != var.targetCompartment
  )
  gpu_memory_shape = can(regex("^BM\\.GPU\\.GB\\d{3}\\S*$", var.cluster_network_shape))

  // display names of instances
  cluster_instances_ids   = var.cluster_network_shape == "BM.GPU.GB200.4" || var.cluster_network_shape == "BM.GPU.GB200-v2.4" || var.cluster_network_shape == "BM.GPU.GB200-v3.4" || var.cluster_network_shape == "BM.GPU.GB300.4" ? data.oci_core_instance.memory_cluster_network_instances.*.id : var.stand_alone ? var.rdma_enabled ? oci_core_instance.compute_cluster_instances.*.id : oci_core_instance.compute_instances.*.id : var.rdma_enabled ? data.oci_core_instance.cluster_network_instances.*.id : data.oci_core_instance.instance_pool_instances.*.id
  cluster_instances_names = var.cluster_network_shape == "BM.GPU.GB200.4" || var.cluster_network_shape == "BM.GPU.GB200-v2.4" || var.cluster_network_shape == "BM.GPU.GB200-v3.4" || var.cluster_network_shape == "BM.GPU.GB300.4" ? data.oci_core_instance.memory_cluster_network_instances.*.display_name : var.stand_alone ? var.rdma_enabled ? oci_core_instance.compute_cluster_instances.*.display_name : oci_core_instance.compute_instances.*.display_name : var.rdma_enabled ? data.oci_core_instance.cluster_network_instances.*.display_name : data.oci_core_instance.instance_pool_instances.*.display_name

  imported_image_urls = distinct(compact([
    var.compute_image_source == "URI" ? var.compute_image_uri : null,
    var.controller_image_source == "URI" ? var.controller_image_uri : null
  ]))

  imported_compute_image_id                   = var.compute_image_source == "URI" ? lookup(lookup(oci_core_image.imported_image, var.compute_image_uri, {}), "id", null) : null
  imported_controller_image_id                = var.controller_image_source == "URI" ? lookup(lookup(oci_core_image.imported_image, var.controller_image_uri, {}), "id", null) : null
  effective_compute_image_source              = var.compute_image_source == "Same as management nodes" ? var.controller_image_source : var.compute_image_source
  effective_compute_image_marketplace_listing = var.compute_image_source == "Same as management nodes" ? var.controller_image_marketplace_listing : var.compute_image_marketplace_listing

  // custom_login_image_ocid      = var.unsupported_login ? var.unsupported_login_image : var.custom_login_image
  // custom_monitoring_image_ocid = var.unsupported_monitoring ? var.unsupported_monitoring_image : var.custom_monitoring_image


  compute_shape       = var.rdma_enabled ? var.cluster_network_shape : var.instance_pool_shape
  instance_pool_ocpus = local.compute_shape == "VM.DenseIO.E4.Flex" ? var.instance_pool_ocpus_denseIO_flex : (local.compute_shape == "VM.DenseIO.E5.Flex" || local.compute_shape == "VM.DenseIO.E6.Ax.Flex") ? var.instance_pool_ocpus_denseIO_e5_e6_flex : var.instance_pool_ocpus
  controller_ocpus    = var.controller_shape == "VM.DenseIO.E4.Flex" ? var.controller_ocpus_denseIO_flex : (var.controller_shape == "VM.DenseIO.E5.Flex" || var.controller_shape == "VM.DenseIO.E6.Ax.Flex") ? var.controller_ocpus_denseIO_e5_e6_flex : var.controller_ocpus
  login_ocpus         = var.login_shape == "VM.DenseIO.E4.Flex" ? var.login_ocpus_denseIO_flex : (var.login_shape == "VM.DenseIO.E5.Flex" || var.login_shape == "VM.DenseIO.E6.Ax.Flex") ? var.login_ocpus_denseIO_e5_e6_flex : var.login_ocpus
  monitoring_ocpus    = var.monitoring_shape == "VM.DenseIO.E4.Flex" ? var.monitoring_ocpus_denseIO_flex : (var.monitoring_shape == "VM.DenseIO.E5.Flex" || var.monitoring_shape == "VM.DenseIO.E6.Ax.Flex") ? var.monitoring_ocpus_denseIO_e5_e6_flex : var.monitoring_ocpus
  // ips of the instances
  cluster_instances_ips       = var.stand_alone ? var.rdma_enabled ? oci_core_instance.compute_cluster_instances.*.private_ip : oci_core_instance.compute_instances.*.private_ip : var.rdma_enabled ? data.oci_core_instance.cluster_network_instances.*.private_ip : data.oci_core_instance.instance_pool_instances.*.private_ip
  first_vcn_ip                = cidrhost(data.oci_core_subnet.private_subnet.cidr_block, 0)
  cluster_instances_ips_index = [for ip in local.cluster_instances_ips : tostring((tonumber(split(".", ip)[3]) - tonumber(split(".", local.first_vcn_ip)[3])) + 256 * (tonumber(split(".", ip)[2]) - tonumber(split(".", local.first_vcn_ip)[2])) + 1)]

  // vcn id derived either from created vcn or existing if specified
  vcn_id = var.use_existing_vcn ? var.vcn_id : element(concat(oci_core_vcn.vcn.*.id, [""]), 0)

  // subnet id derived either from created subnet or existing if specified
  //  subnet_id = var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0)
  subnet_id = var.private_deployment ? var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 1) : var.use_existing_vcn ? var.private_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0)

  nfs_source_IP                = var.add_nfs && var.create_fss == "new" ? (var.mount_target_count == 0 ? oci_dns_rrset.config_fss.domain : oci_dns_rrset.fss-dns-round-robin[0].domain) : var.nfs_source_IP
  nfs_list_of_mount_target_IPs = var.add_nfs && var.create_fss == "new" ? (var.mount_target_count == 0 ? "[\"${oci_file_storage_mount_target.config_fss_mount_target.ip_address}\"]" : "[\"${join("\",\"", oci_file_storage_mount_target.FSSMountTarget.*.ip_address)}\"]") : var.nfs_source_IP
  config_fss_hostname          = "fss-config-${local.cluster_name}.${local.zone_name}"

  // subnet id derived either from created subnet or existing if specified
  // controller_subnet_id = var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, [""]), 0)
  controller_subnet_id = var.private_deployment ? var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.private-subnet.*.id, [""]), 0) : var.use_existing_vcn ? var.public_subnet_id : element(concat(oci_core_subnet.public-subnet.*.id, [""]), 0)

  cluster_name = var.use_custom_name ? lower(var.cluster_name) : random_pet.name.id

  controller_image = (
    var.controller_image_source == "Marketplace" ? oci_core_app_catalog_subscription.controller_mp_image_subscription[0].listing_resource_id :
    var.controller_image_source == "Unlisted" ? var.controller_image_unlisted_ocid :
    var.controller_image_source == "Custom" ? var.controller_image_ocid :
    local.imported_controller_image_id
  )

  compute_image = (
    var.compute_image_source == "Same as management nodes" ? local.controller_image :
    var.compute_image_source == "Marketplace" ? oci_core_app_catalog_subscription.mp_image_subscription[0].listing_resource_id :
    var.compute_image_source == "Unlisted" ? var.compute_image_unlisted_ocid :
    var.compute_image_source == "Custom" ? var.compute_image_ocid :
    local.imported_compute_image_id
  )

  is_controller_flex_shape = length(regexall(".*VM.*.*(Flex|Generic)$", var.controller_shape)) > 0 ? [local.controller_ocpus] : []
  is_login_flex_shape      = length(regexall(".*VM.*.*(Flex|Generic)$", var.login_shape)) > 0 ? [local.login_ocpus] : []
  is_monitoring_flex_shape = length(regexall(".*VM.*.*(Flex|Generic)$", var.monitoring_shape)) > 0 ? [local.monitoring_ocpus] : []

  is_instance_pool_flex_shape = length(regexall(".*VM.*.*(Flex|Generic)$", var.instance_pool_shape)) > 0 ? [local.instance_pool_ocpus] : []

  queue_ocid = oci_queue_queue.queue.id
  // Cluster OCID

  host                = var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip[0].ip_address : oci_core_instance.controller.public_ip
  controller_bool_ip  = var.private_deployment ? false : true
  login_bool_ip       = var.private_deployment ? false : true
  monitoring_bool_ip  = var.private_deployment ? false : true
  controller_subnet   = var.private_deployment ? oci_core_subnet.private-subnet : oci_core_subnet.public-subnet
  private_subnet_cidr = var.private_deployment ? [var.public_subnet, var.private_subnet] : [var.private_subnet]
  host_backup         = var.slurm_ha ? var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip_backup[0].ip_address : oci_core_instance.backup[0].public_ip : "none"
  host_login          = var.login_node ? var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip_login[0].ip_address : oci_core_instance.login[0].public_ip : "none"
  host_monitoring     = var.monitoring_node ? var.private_deployment ? data.oci_resourcemanager_private_endpoint_reachable_ip.private_endpoint_reachable_ip_monitoring[0].ip_address : oci_core_instance.monitoring[0].public_ip : "none"

  timeout_per_batch = var.rdma_enabled ? 30 : 15
  timeout_ip        = join("", [((var.node_count - (var.node_count % 20)) / 20 + 1) * local.timeout_per_batch, "m"])

  zone_name     = var.use_existing_vcn ? var.zone_name : "${local.cluster_name}.local"
  platform_type = local.compute_shape == "BM.GPU4.8" ? "AMD_ROME_BM_GPU" : local.compute_shape == "BM.GPU.B4.8" || local.compute_shape == "BM.GPU.A100-v2.8" ? "AMD_MILAN_BM_GPU" : local.compute_shape == "BM.Standard.E3.128" ? "AMD_ROME_BM" : local.compute_shape == "BM.Standard.E4.128" || local.compute_shape == "BM.DenseIO.E4.128" ? "AMD_MILAN_BM" : "GENERIC_BM"

  // variables to create functions and events
  ocir_namespace   = lookup(data.oci_objectstorage_namespace.namespace, "namespace")
  compartment_name = lookup(data.oci_identity_compartment.compartment, "name")
  region_key       = [for d in flatten(data.oci_identity_regions.regions.regions) : lower(d.key) if d.name == var.region][0]
  auth_token       = (var.use_OCI_generated_container && !var.is_gov_cloud) ? "" : var.use_existing_auth_token ? var.auth_token : sensitive(oci_identity_auth_token.auth_token[0].token)
  registry_id      = (var.use_OCI_generated_container && !var.is_gov_cloud) ? "" : var.use_existing_registry ? var.registry_id : oci_artifacts_container_repository.container_repository[0].id
  ocir_login_user = var.login_to_ocir_using_default_domain ? (
    # Default domain: namespace/username  (no domain prefix needed)
    "${local.ocir_namespace}/${data.oci_identity_user.ocir_login_user_default_domain[0].name}"
    ) : (
    # Non-default domain: namespace/domain-display-name/username
    "${local.ocir_namespace}/${data.oci_identity_domain.ocir_login_custom_domain[0].display_name}/${data.oci_identity_domains_user.ocir_login_user_custom_domain[0].user_name}"
  )
  topic_id            = var.alerting ? oci_ons_notification_topic.grafana_alerts[0].id : ""
  metrics_stream_ocid = var.ingest_oci_metrics ? oci_streaming_stream.telegraf_stream[0].id : ""
  # Gov Regions
  gov_cloud_regions = toset(["us-langley-1", "us-luke-1"])
  #is_gov_cloud = contains(local.gov_cloud_regions, var.region) || can(regex("-gov-", var.region))
  ocir_host  = var.is_gov_cloud ? "ocir.${var.region}.oci.oraclegovcloud.com" : "${local.region_key}.ocir.io"
  ocir_image = (var.is_gov_cloud || !var.use_OCI_generated_container) ? "${local.ocir_host}/${local.ocir_namespace}/${data.oci_artifacts_container_repository.container_repo[0].display_name}:${var.container_version}" : "${local.ocir_host}/${var.OCI_generated_container_namespace}/${var.OCI_generated_container_name}:${var.container_version}"
  # Pick the right IP based on flags

  lustre_IP                          = var.add_lfs && var.create_lfs == "new" ? oci_lustre_file_storage_lustre_file_system.lustre_file_system[0].management_service_address : var.lfs_source_IP
  slurm_monitoring_mysql_backend     = var.slurm && var.slurm_ha ? "managed" : var.slurm_monitoring_mysql_backend
  slurm_job_monitoring_enabled       = var.slurm && var.cluster_monitoring && var.slurm_job_monitoring
  slurm_monitoring_db_required       = local.slurm_job_monitoring_enabled
  slurm_monitoring_use_managed_mysql = local.slurm_monitoring_db_required && local.slurm_monitoring_mysql_backend == "managed"
  create_managed_mysql               = (var.slurm && var.slurm_ha) || local.slurm_monitoring_use_managed_mysql
  mysql_service_host                 = local.create_managed_mysql ? data.oci_mysql_mysql_db_system.slurm_mysql[0].endpoints[0].ip_address : ""
  slurm_monitoring_db_host           = local.slurm_monitoring_db_required ? (local.slurm_monitoring_use_managed_mysql ? local.mysql_service_host : oci_core_instance.controller.private_ip) : ""
  mysql_admin_username               = trimspace(var.mysql_admin_username) != "" ? trimspace(var.mysql_admin_username) : "admin"
  mysql_admin_password               = trimspace(var.mysql_admin_password) != "" ? var.mysql_admin_password : random_password.mysql_admin_pwd.result
  monitoring_group_vars              = <<-EOT
    grafana_initial_creds: !unsafe ${jsonencode(base64encode(random_password.grafana_admin_pwd.result))}
    mysql_admin_password: !unsafe ${jsonencode(local.mysql_admin_password)}
    slurm_monitoring_db_password: !unsafe ${jsonencode(random_password.slurm_monitoring_db_pwd.result)}
    slurm_monitoring_grafana_db_password: !unsafe ${jsonencode(random_password.slurm_monitoring_grafana_db_pwd.result)}
  EOT
  detected_arch                      = data.external.architecture.result["arch"]
  function_shape = var.is_gov_cloud ? "GENERIC_X86" : (
    var.use_OCI_generated_container ? "GENERIC_X86_ARM" : (
      local.detected_arch == "aarch64" ? "GENERIC_ARM" :
      # otherwise
      "GENERIC_X86"
    )
  )
  bucket_access_key = var.create_bucket ? oci_identity_customer_secret_key.customer_secret_key[0].id : ""
  bucket_secret_key = var.create_bucket ? oci_identity_customer_secret_key.customer_secret_key[0].key : ""
}
