resource "oci_core_instance" "monitoring" {
  count               = var.monitoring_node ? 1 : 0
  depends_on          = [oci_core_subnet.public-subnet]
  availability_domain = var.monitoring_ad
  compartment_id      = var.targetCompartment
  shape               = var.monitoring_shape

  dynamic "shape_config" {
    for_each = local.is_monitoring_flex_shape
    content {
      ocpus         = shape_config.value
      memory_in_gbs = var.monitoring_custom_memory ? var.monitoring_memory : 16 * shape_config.value
    }
  }
  agent_config {
    is_management_disabled = true
  }
  display_name = "${local.cluster_name}-monitoring"

  freeform_tags = {
    "cluster_name"   = local.cluster_name
    "parent_cluster" = local.cluster_name
  }

  metadata = {
    ssh_authorized_keys = "${var.ssh_key}\n${tls_private_key.ssh.public_key_openssh}"
    user_data           = base64encode(local.controller_config)
  }
  source_details {
    source_id               = local.monitoring_image
    boot_volume_size_in_gbs = var.monitoring_boot_volume_size
    boot_volume_vpus_per_gb = 30
    source_type             = "image"
  }

  create_vnic_details {
    subnet_id        = local.controller_subnet_id
    assign_public_ip = local.monitoring_bool_ip
    freeform_tags = {
      "cluster_name"   = local.cluster_name
      "parent_cluster" = local.cluster_name
    }
  }
}

resource "oci_dns_rrset" "rrset-monitoring" {
  count           = var.monitoring_node && var.dns_entries ? 1 : 0
  zone_name_or_id = data.oci_dns_zones.dns_zones.zones[0].id
  domain          = "${var.monitoring_node ? oci_core_instance.monitoring[0].display_name : ""}.${local.zone_name}"
  rtype           = "A"
  items {
    domain = "${var.monitoring_node ? oci_core_instance.monitoring[0].display_name : ""}.${local.zone_name}"
    rtype  = "A"
    rdata  = var.monitoring_node ? oci_core_instance.monitoring[0].private_ip : ""
    ttl    = 3600
  }
  scope   = "PRIVATE"
  view_id = data.oci_dns_views.dns_views.views[0].id
}


resource "random_password" "grafana_admin_pwd" {
  length           = 16
  override_special = "-_@"
  min_upper        = 1
  min_lower        = 1
  min_special      = 1
  min_numeric      = 1
}

resource "oci_streaming_stream" "telegraf_stream" {
  count          = var.cluster_monitoring && var.ingest_oci_metrics ? 1 : 0

  name           = "${local.cluster_name}-stream"
  partitions     = 1
  compartment_id = var.targetCompartment

  freeform_tags = {
    "cluster_name"   = local.cluster_name
    "parent_cluster" = local.cluster_name
  }

  retention_in_hours = 24
}

resource "oci_sch_service_connector" "telegraf_service_connector" {
  count          = var.cluster_monitoring && var.ingest_oci_metrics ? 1 : 0

  compartment_id = var.targetCompartment
  display_name   = "${local.cluster_name}-metrics-exporter"
  
  source {
    kind = "monitoring"

    monitoring_sources {
      compartment_id = var.targetCompartment
      
      namespace_details {
        kind = "selected"
        dynamic "namespaces" {
          for_each = ["oci_blockstore", "oci_fastconnect", "oci_filestorage", "oci_internet_gateway", "oci_lustrefilesystem", "oci_objectstorage", "oci_nat_gateway", "oci_service_gateway", "oci_vcn", "oci_dynamic_routing_gateway"] # "gpu_infrastructure_health", "rdma_infrastructure_health"
          content {
            metrics {
              kind = "all"
            }
            namespace = namespaces.value
          }
        }     
      }
    }
  }

  target {
    kind      = "streaming"
    stream_id = oci_streaming_stream.telegraf_stream[0].id
  }

  description   = "Service connector hub used to export OCI metrics to Prometheus for Slurm cluster ${local.cluster_name}"
  freeform_tags = {
    "cluster_name"   = local.cluster_name
    "parent_cluster" = local.cluster_name
  }
}
