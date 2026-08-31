variable "region" {
  type = string
}
variable "tenancy_ocid" {
  type = string
}
variable "targetCompartment" {
  type = string
}
variable "ad" {
  type = string
}

variable "ssh_key" {
  type = string
}
variable "compute_node_ssh_key" {
  type    = string
  default = ""
}
variable "rdma_enabled" {
  default = true
  type    = bool
}
variable "stand_alone" {
  default = false
  type    = bool
}
variable "compute_cluster_exists" {
  default = false
  type    = bool
}
variable "compute_cluster_id" {
  default = ""
  type    = string
}
variable "memory_fabric_id" {
  default = ""
  type    = string
}
variable "use_custom_name" {
  default = false
  type    = bool
}
variable "cluster_name" {
  default = "custom-cluster-name-123"
  type    = string
  validation {
    condition     = can(regex("^[-a-z0-9]+$", var.cluster_name))
    error_message = "The name of the cluster (must be lower case letters, digits and -)."
  }
}
variable "controller_ad" {
  type = string
}
variable "controller_shape" {
  default = "VM.Standard2.4"
  type    = string
}

variable "controller_image_ocid" {
  type    = string
  default = null
}
variable "controller_image_uri" {
  type    = string
  default = null
}
variable "controller_boot_volume_size" {
  type = number
}
variable "controller_boot_volume_backup" {
  type = bool
}
variable "controller_boot_volume_backup_type" {
  default = "INCREMENTAL"
  type    = string
}
variable "controller_boot_volume_backup_period" {
  default = "ONE_DAY"
  type    = string
}
variable "controller_boot_volume_backup_retention_seconds" {
  default = "7776000"
  type    = string
}
variable "controller_boot_volume_backup_time_zone" {
  default = "REGIONAL_DATA_CENTER_TIME"
  type    = string
}
variable "cluster_network_shape" {
  default = "BM.HPC2.36"
  type    = string
}
variable "instance_pool_shape" {
  default = "VM.Standard2.4"
  type    = string
}
variable "node_count" {
  default = 2
  type    = number
}
variable "boot_volume_size" {
  default = 50
  type    = number
}
variable "compute_image_ocid" {
  default = null
  type    = string
}
variable "compute_image_unlisted_ocid" {
  default = null
  type    = string
}
variable "compute_image_uri" {
  type    = string
  default = null
}
variable "controller_image_unlisted_ocid" {
  default = null
  type    = string
}
variable "vcn_compartment" {
  default = ""
  type    = string
}
variable "vcn_id" {
  default = ""
  type    = string
}
variable "create_private_zone" {
  type    = bool
  default = false
}
variable "use_existing_vcn" {
  type    = bool
  default = false
}
variable "public_subnet_id" {
  default = ""
  type    = string
}
variable "private_subnet_id" {
  default = ""
  type    = string
}
variable "vcn_subnet" {
  default = "172.16.0.0/21"
  type    = string
}
variable "public_subnet" {
  default = "172.16.0.0/24"
  type    = string
}

variable "rdma_subnet" {
  default = "192.168.0.0/16"
  type    = string
}
variable "private_subnet" {
  default = "172.16.4.0/22"
  type    = string
}
variable "ssh_cidr" {
  default = "0.0.0.0/0"
  type    = string
}
variable "slurm" {
  default = false
  type    = bool
}
variable "slurm_version" {
  default = "26.05.0-1.oci"
  type    = string
}
variable "slurm_ha" {
  default = false
  type    = bool
}
variable "slurm_federation" {
  default = false
  type    = bool
}

variable "ip_slurmdbd" {
  default = ""
  type    = string
}

variable "munge_key" {
  default = ""
  type    = string
}
variable "login_node" {
  default = true
  type    = bool
}
variable "login_ad" {
  default = ""
  type    = string
}
variable "login_shape" {
  default = "VM.Standard2.4"
  type    = string
}
variable "login_boot_volume_size" {
  default = 50
  type    = number
}
variable "monitoring_node" {
  default = false
  type    = bool
}
variable "monitoring_ad" {
  default = ""
  type    = string
}
variable "monitoring_shape" {
  default = "VM.Standard2.4"
  type    = string
}
variable "monitoring_boot_volume_size" {
  default = 50
  type    = number
}
variable "ldap" {
  default = true
  type    = bool
}
variable "spack" {
  default = false
  type    = bool
}
variable "controller_ocpus" {
  default = 2
  type    = number
}
variable "controller_ocpus_denseIO_flex" {
  default = 8
  type    = number
}
variable "controller_ocpus_denseIO_e5_e6_flex" {
  default = 8
  type    = number
}
variable "instance_pool_ocpus" {
  default = 2
  type    = number
}
variable "instance_pool_ocpus_denseIO_flex" {
  default = 8
  type    = number
}
variable "instance_pool_ocpus_denseIO_e5_e6_flex" {
  default = 8
  type    = number
}
variable "instance_pool_memory" {
  default = 16
  type    = number
}
variable "instance_pool_custom_memory" {
  default = false
  type    = bool
}
variable "login_ocpus" {
  default = 2
  type    = number
}
variable "login_ocpus_denseIO_flex" {
  default = 8
  type    = number
}
variable "login_ocpus_denseIO_e5_e6_flex" {
  default = 8
  type    = number
}
variable "monitoring_ocpus" {
  default = 2
  type    = number
}
variable "monitoring_ocpus_denseIO_flex" {
  default = 8
  type    = number
}
variable "monitoring_ocpus_denseIO_e5_e6_flex" {
  default = 8
  type    = number
}
variable "controller_memory" {
  default = 16
  type    = number
}
variable "controller_custom_memory" {
  default = false
  type    = bool
}
variable "login_memory" {
  default = 16
  type    = number
}
variable "login_custom_memory" {
  default = false
  type    = bool
}
variable "monitoring_memory" {
  default = 16
  type    = number
}
variable "monitoring_custom_memory" {
  default = false
  type    = bool
}
variable "privilege_sudo" {
  default = true
  type    = bool
}
variable "privilege_group_name" {
  default = "privilege"
  type    = string
}


variable "compute_image_marketplace_listing" {
  default = "HPC_OL8"
  type    = string
}
variable "marketplace_version_id" {
  type = map(string)
  default = {
    "HPC_OL8"        = "Oracle-Linux-8.10-2025.06.17-0-RHCK-OFED-24.10-1.1.4.0-2025.07.19-0"
    "GPU_OL8_NV550"  = "Oracle-Linux-8.10-2025.06.17-0-RHCK-OFED-24.10-1.1.4.0-GPU-550-CUDA-12.4-2025.07.19-0"
    "GPU_OL8_NV570"  = "Oracle-Linux-8.10-2025.06.17-0-RHCK-OFED-24.10-1.1.4.0-GPU-570-OPEN-CUDA-12.8-2025.07.18-0"
    "GPU_OL8_AMD632" = "Oracle-Linux-8.10-2025.06.17-0-RHCK-OFED-24.10-1.1.4.0-AMD-ROCM-632-2025.07.20-0"
  }
}

# To find the Appcatalog OCID, run
# oci compute pic listing list --display-name "Oracle Linux 7 - HPC Cluster Networking Image"

variable "marketplace_listing_id_HPC" {
  default = "ocid1.appcataloglisting.oc1..aaaaaaaahz2xiwfcsbebmqg7sp6lhdt6r2vsjro5jfukkl5cntlqvfhkbzaq"
  type    = string
}
variable "marketplace_listing_id_GPU" {
  default = "ocid1.appcataloglisting.oc1..aaaaaaaab2hkpxsglxfbzitiiqv6djxzj5q5soxotwdem2dd2kbifgk4p55q"
  type    = string
}
variable "shared_home" {
  default = "nfs"
  type    = string
}
variable "create_bucket" {
  default = false
  type    = bool
}
variable "hyperthreading" {
  default = true
  type    = bool
}
variable "add_nfs" {
  default = false
  type    = bool
}
variable "create_fss" {
  default = "existing"
  type    = string
}
variable "enable_fss_deletion_protection" {
  default = true
  type    = bool
}
variable "mount_target_count" {
  default = "0"
  type    = number
}
variable "fss_compartment" {
  default = ""
  type    = string
}
variable "fss_ad" {
  default = ""
  type    = string
}
variable "nfs_target_path" {
  default = "/fss"
  type    = string
}
variable "nfs_source_IP" {
  default = ""
  type    = string
}
variable "nfs_list_of_mount_target_IPs" {
  default = ""
  type    = string
}
variable "nfs_source_path" {
  default = "/fss"
  type    = string
}
variable "nfs_options" {
  default = ""
  type    = string
}
variable "cluster_monitoring" {
  default = false
  type    = bool
}
variable "slurm_job_monitoring" {
  default = false
  type    = bool
}
variable "slurm_monitoring_mysql_backend" {
  default = "managed"
  type    = string

  validation {
    condition     = contains(["local", "managed"], var.slurm_monitoring_mysql_backend)
    error_message = "slurm_monitoring_mysql_backend must be either local or managed."
  }
}
variable "grafana_ldap_auth_enabled" {
  default = false
  type    = bool
}
variable "alerting" {
  default = false
  type    = bool
}
variable "pyxis" {
  default = false
  type    = bool
}
variable "dgxc_benchmarking" {
  default = false
  type    = bool
}
variable "pam" {
  default = false
  type    = bool
}
variable "sacct_limits" {
  default = false
  type    = bool
}

variable "queue" {
  default = "compute"
  type    = string
}

variable "controller_image_source" {
  type    = string
  default = "Marketplace"

  validation {
    condition     = contains(["Marketplace", "Unlisted", "Custom", "URI"], var.controller_image_source)
    error_message = "Valid values for controller image source: Marketplace, Unlisted, Custom, URI."
  }
}

variable "controller_username" {
  type    = string
  default = ""
}

variable "compute_image_source" {
  type    = string
  default = "Marketplace"

  validation {
    condition     = contains(["Marketplace", "Unlisted", "Custom", "URI", "Same as management nodes"], var.compute_image_source)
    error_message = "Valid values for compute image source: Marketplace, Unlisted, Custom, URI, Same as management nodes."
  }
}

variable "compute_username" {
  type    = string
  default = ""
}

variable "private_deployment" {
  default = false
  type    = bool
}

variable "localdisk" {
  default = true
  type    = bool
}
variable "log_vol" {
  default = true
  type    = bool
}
variable "redundancy" {
  default = false
  type    = bool
}
variable "controller_image_marketplace_listing" {
  default = "HPC_OL8"
  type    = string
}
variable "zone_name" {
  default = ""
  type    = string
}
variable "healthchecks" {
  default = true
  type    = bool
}
variable "active_healthchecks" {
  default = true
  type    = bool
}

variable "BIOS" {
  default = false
  type    = bool
}
variable "IOMMU" {
  default = false
  type    = bool
}
variable "SMT" {
  default = true
  type    = bool
}
variable "virt_instr" {
  default = false
  type    = bool
}
variable "access_ctrl" {
  default = false
  type    = bool
}
variable "numa_nodes_per_socket" {
  default = "Default"
  type    = string
}
variable "percentage_of_cores_enabled" {
  default = "Default"
  type    = string
}
variable "change_hostname" {
  default = false
  type    = bool
}
variable "hostname_convention" {
  default = "None"
  type    = string
}

variable "current_user_ocid" {
  default = ""
  type    = string
}

variable "use_existing_registry" {
  default = false
  type    = bool
}

variable "registry_id" {
  default = ""
  type    = string
}

variable "use_existing_auth_token" {
  default = false
  type    = bool
}

variable "auth_token" {
  default = ""
  type    = string
}

variable "home_region" {
  default = "us-ashburn-1"
  type    = string
}

variable "is_gov_cloud" {
  default = false
  type    = bool
}

variable "use_OCI_generated_container" {
  default = true
  type    = bool
}

variable "OCI_generated_container_namespace" {
  default = "hpc_limited_availability"
  type    = string
}

variable "OCI_generated_container_name" {
  default = "oci-hpc-stack"
  type    = string
}


variable "container_version" {
  default = "release-3.1.1"
  type    = string
}


variable "ondemand_partition" {
  default = false
  type    = bool
}

variable "ondemand_partition_count" {
  default = 100
  type    = number
}

variable "preemptible" {
  default = false
  type    = bool
}

variable "add_lfs" {
  default = false
  type    = bool
}
variable "create_lfs" {
  default = false
  type    = string
}
variable "lfs_compartment" {
  default = ""
  type    = string
}
variable "lfs_ad" {
  default = ""
  type    = string
}
variable "lfs_capacity_in_gbs" {
  default = 31200
  type    = number
}
variable "lfs_perf_tier" {
  default = "MBPS_PER_TB_125"
  type    = string
}
variable "lfs_freeform_tag_key" {
  default = ""
  type    = string
}
variable "lfs_freeform_tag_value" {
  default = ""
  type    = string
}
variable "lfs_target_path" {
  default = "/mnt/lfs"
  type    = string
}
variable "lfs_source_IP" {
  default = "0.0.0.0"
  type    = string
}
variable "lfs_source_path" {
  default = "lustrefs"
  type    = string
}
variable "lfs_options" {
  default = "defaults,_netdev"
  type    = string
}
variable "ingest_oci_metrics" {
  default = false
  type    = bool
}

variable "mysql_admin_password" {
  default = ""
  type    = string

  validation {
    condition = var.mysql_admin_password == "" || (
      length(var.mysql_admin_password) >= 8 &&
      length(var.mysql_admin_password) <= 32 &&
      can(regex("[!@#%^*_+\\-:?.,\\[\\]{}]", var.mysql_admin_password)) &&
      can(regex("[0-9]", var.mysql_admin_password)) &&
      can(regex("[a-z]", var.mysql_admin_password)) &&
      can(regex("[A-Z]", var.mysql_admin_password)) &&
      !can(regex("[$()]", var.mysql_admin_password))
    )
    error_message = "mysql_admin_password must be 8–32 characters and contain uppercase, lowercase, numeric, and permitted special characters; $, (, and ) are not allowed."
  }
}

variable "mysql_shape" {
  default = "MySQL.4"
  type    = string
}

variable "mysql_admin_username" {
  default = ""
  type    = string
}

variable "wildcard_dns_domain" {
  default = "endpoint.oci-hpc.ai"
  type    = string
}

variable "use_lets_encrypt_prod_ep" {
  default = true
  type    = bool
}

variable "create_policies" {
  default     = false
  type        = bool
  description = "Create IAM policies for the Slurm controller and function resource principals."
}

variable "use_existing_dynamic_group" {
  default     = false
  type        = bool
  description = "Use an existing dynamic group for created policies instead of creating a new one."
}

variable "dynamic_group_id" {
  default     = ""
  type        = string
  description = "Existing dynamic group OCID."
}

variable "identity_domain_compartment_id" {
  default     = null
  type        = string
  description = "Compartment OCID containing the selected identity domain."
}

variable "use_default_identity_domain" {
  default     = true
  type        = bool
  description = "Use the default identity domain."
}

variable "identity_domain_ocid" {
  type        = string
  description = "Identity domain OCID for the user; overrides default identity domain."
  default     = null
}

variable "prechecks" {
  default = true
  type    = bool
}

variable "login_to_ocir_using_default_domain" {
  type        = bool
  default     = true
  description = "Using default domain to generate login user for OCIR."
}

variable "custom_domain_ocid_to_authenticate_to_ocir" {
  type        = string
  default     = null
  description = "Using custom domain to generate login user for OCIR."
}
