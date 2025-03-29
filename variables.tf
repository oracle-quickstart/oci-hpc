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
variable "secondary_ad" { 
  default = ""
  type = string
  }
variable "third_ad" { 
  default = "" 
  type = string
  }
variable "use_multiple_ads" { 
  default = false 
  type = bool
  }
variable "ssh_key" {
  type = string
}
variable "compute_node_ssh_key" {
  type = string
  default = "" 
}

variable "cluster_network" { 
  default = true 
  type = bool
  }
variable "compute_cluster" { 
  default = false 
  type = bool
  }
variable "compute_cluster_exists" { 
  default = false 
  type = bool
  }
variable "compute_cluster_id" { 
  default = "" 
  type = string
  }
variable "compute_cluster_start_index" { 
  default = 0 
  type = number
  }
variable "use_custom_name" { 
  default = false 
  type = bool
  }
variable "cluster_name" { 
  default = "" 
  type = string
  }
variable "controller_ad" {
  type = string
}
variable "controller_shape" { 
  default = "VM.Standard2.4" 
  type = string
  }
variable "controller_object_storage_par" { 
  default = true 
  type = bool
  }

variable "custom_controller_image" {
  type    = string
  default = "image.ocid"
}
variable "custom_login_image" {
  type    = string
  default = "image.ocid"
}
variable "custom_monitoring_image" {
  type    = string
  default = "image.ocid"
}
variable "controller_boot_volume_size" {
  type = number
}
variable "controller_boot_volume_backup" {
  type = bool
}
variable "controller_boot_volume_backup_type" { 
  default = "INCREMENTAL" 
  type = string
  }
variable "controller_boot_volume_backup_period" { 
  default = "ONE_DAY" 
  type = string
  }
variable "controller_boot_volume_backup_retention_seconds" { 
  default = "7776000" 
  type = string
  }
variable "controller_boot_volume_backup_time_zone" { 
  default = "REGIONAL_DATA_CENTER_TIME" 
  type = string
  }
variable "cluster_network_shape" { 
  default = "BM.HPC2.36" 
  type = string
  }
variable "instance_pool_shape" { 
  default = "VM.Standard2.4" 
  type = string
  }
variable "node_count" { 
  default = 2 
  type = number
  }
variable "boot_volume_size" { 
  default = 50 
  type = number
  }
variable "use_marketplace_image" { 
  default = true 
  type = bool
  }
variable "image" { 
  default = "ocid1.image.oc1..aaaaaaaa5yxem7wzie34hi5km4qm2t754tsfxrjuefyjivebrxjad4jcj5oa" 
  type = string
  }
variable "image_ocid" { 
  default = "ocid1.image.oc1..aaaaaaaa5yxem7wzie34hi5km4qm2t754tsfxrjuefyjivebrxjad4jcj5oa" 
  type = string
  }
variable "use_compute_agent" { 
  default = true 
  type = bool
  }
variable "unsupported_controller_image" { 
  default = "" 
  type = string
  }
variable "unsupported_login_image" { 
  default = "" 
  type = string
  }
variable "unsupported_monitoring_image" { 
  default = "" 
  type = string
  }
variable "use_cluster_nfs" { 
  default = true 
  type = bool
  }
variable "use_scratch_nfs" { 
  default = false 
  type = bool
  }
variable "cluster_nfs_path" { 
  default = "/nfs/cluster" 
  type = string
  }
variable "scratch_nfs_path" { 
  default = "/nfs/scratch" 
  type = string
  }
variable "vcn_compartment" { 
  default = "" 
  type = string
  }
variable "vcn_id" { 
  default = "" 
  type = string
  }
variable "use_existing_vcn" { 
  type = bool 
  default = false 
  }
variable "public_subnet_id" { 
  default = "" 
  type = string
  }
variable "private_subnet_id" { 
  default = "" 
  type = string
  }
variable "vcn_subnet" { 
  default = "172.16.0.0/21" 
  type = string
  }
variable "public_subnet" { 
  default = "172.16.0.0/24" 
  type = string
  }
variable "additional_subnet" { 
  default = "172.16.1.0/24"
  type = string
  }
variable "rdma_subnet" { 
  default = "192.168.0.0/16" 
  type = string
  }
variable "private_subnet" { 
  default = "172.16.4.0/22"
  type = string
  }
variable "ssh_cidr" { 
  default = "0.0.0.0/0" 
  type = string
  }
variable "slurm" { 
  default = false 
  type = bool
  }
variable "slurm_ha" { 
  default = false
  type = bool
  }
variable "login_node" { 
  default = true 
  type = bool
  }
variable "login_ad" { 
  default = ""
  type = string
  }
variable "login_shape" { 
  default = "VM.Standard2.4"
  type = string
  }
variable "login_boot_volume_size" { 
  default = 50
  type = number
  }
variable "monitoring_node" { 
  default = false
  type = bool
  }
variable "monitoring_ad" { 
  default = ""
  type = string
  }
variable "monitoring_shape" { 
  default = "VM.Standard2.4"
  type = string
  }
variable "monitoring_boot_volume_size" { 
  default = 50
  type = number
  }
variable "slurm_nfs" { 
  default = false
  type = bool
  }
variable "rack_aware" { 
  default = false
  type = bool
  }
variable "ldap" { 
  default = true
  type = bool
  }
variable "spack" { 
  default = false
  type = bool
  }
variable "controller_ocpus" { 
  default = 2
  type = number
  }
variable "controller_ocpus_denseIO_flex" { 
  default = 8
  type = number
  }
variable "instance_pool_ocpus" { 
  default = 2
  type = number
  }
variable "instance_pool_ocpus_denseIO_flex" { 
  default = 8
  type = number
  }
variable "instance_pool_memory" { 
  default = 16
  type = number
  }
variable "instance_pool_custom_memory" { 
  default = false
  type = bool
  }
variable "login_ocpus" { 
  default = 2
  type = number
  }
variable "login_ocpus_denseIO_flex" { 
  default = 8
  type = number
  }
variable "monitoring_ocpus" {
   default = 2
   type = number
  }
variable "monitoring_ocpus_denseIO_flex" { 
  default = 8
  type = number
  }
variable "controller_memory" { 
  default = 16
  type = number
  }
variable "controller_custom_memory" { 
  default = false
  type = bool
  }
variable "login_memory" { 
  default = 16
  type = number
  }
variable "login_custom_memory" { 
  default = false
  type = bool
  }
variable "monitoring_memory" { 
  default = 16
  type = number
  }
variable "monitoring_custom_memory" { 
  default = false
  type = bool
  }
variable "privilege_sudo" { 
  default = true
  type = bool
  }
variable "privilege_group_name" { 
  default = "privilege"
  type = string
  }


variable "marketplace_listing" {
  default = "HPC_OL8"
  type = string
}
variable "marketplace_version_id" {
  type = map(string)
  default = {
    "HPC_OL8"       = "Oracle-Linux-8.10-2025.02.28-0-OCA-RHCK-OFED-24.10-1.1.4.0-2025.03.27-0"
    "GPU_OL8_NV550" = "Oracle-Linux-8.10-2025.02.28-0-OCA-RHCK-OFED-24.10-1.1.4.0-GPU-550-CUDA-12.4-2025.03.27-0"
    "GPU_OL8_NV560" = "Oracle-Linux-8.10-2025.02.28-0-OCA-RHCK-OFED-24.10-1.1.4.0-GPU-550-CUDA-12.4-2025.03.27-0"
    "GPU_OL8_NV570" = "Oracle-Linux-8.10-2025.02.28-0-OCA-RHCK-OFED-24.10-1.1.4.0-GPU-550-CUDA-12.4-2025.03.27-0"
    "GPU_OL8_AMD632" = "Oracle-Linux-8.10-2025.02.28-0-OCA-RHCK-OFED-24.10-1.1.4.0-AMD-ROCM-632-2025.03.28-0"
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
variable "controller_block_volume_performance" {
  /* 
  Allowed values 
  "0.  Lower performance"
  "10. Balanced performance"
  "20. High Performance"
*/

  default = "10. Balanced performance"
  type = string

}

variable "controller_block" {
  default = false
  type = bool
}

variable "controller_block_volume_size" {
  default = 1000
  type = number
}

variable "login_block_volume_performance" {
  /* 
  Allowed values 
  "0.  Lower performance"
  "10. Balanced performance"
  "20. High Performance"
*/

  default = "10. Balanced performance"
  type = string
}
variable "login_block" {
  default = false
  type = bool
}

variable "login_block_volume_size" {
  default = 1000
  type = number
}
variable "scratch_nfs_type_cluster" { 
  default = "nvme"
  type = string
  }
variable "scratch_nfs_type_pool" { 
  default = "none"
  type = string
  }
variable "cluster_block_volume_size" { 
  default = "1000"
  type = string
  }
variable "cluster_block_volume_performance" { 
  default = "10. Balanced performance"
  type = string
  }

variable "inst_prin" { 
  default = true
  type = bool
  }
variable "api_user_key" { 
  default = ""
  type = string
  }
variable "api_fingerprint" { 
  default = ""
  type = string
  }
variable "api_user_ocid" { 
  default = ""
  type = string
  }
variable "home_nfs" { 
  default = true
  type = bool
  }
variable "home_fss" { 
  default = false
  type = bool
  }
variable "configure" { 
  default = true
  type = bool
  }

variable "hyperthreading" { 
  default = true
  type = bool
  }

variable "autoscaling" { 
  default = false
  type = bool
  }
variable "latency_check" { 
  default = true
  type = bool
  }
variable "add_nfs" { 
  default = false
  type = bool
  }
variable "create_fss" { 
  default = false
  type = bool
  }
variable "mount_target_count" { 
  default = 1
  type = number
  }
variable "fss_compartment" { 
  default = ""
  type = string
  }
variable "fss_ad" { 
  default = ""
  type = string
  }
variable "nfs_target_path" { 
  default = "/fss"
  type = string
  }
variable "nfs_source_IP" { 
  default = ""
  type = string
  }
variable "nfs_list_of_mount_target_IPs" { 
  default = ""
  type = string
  }
variable "nfs_source_path" { 
  default = "/fss"
  type = string
  }
variable "nfs_options" { 
  default = ""
  type = string
  }
variable "enroot" { 
  default = false
  type = bool
  }
variable "cluster_monitoring" { 
  default = false
  type = bool
  }
variable "alerting" { 
  default = false
  type = bool
  }
variable "pyxis" { 
  default = false
  type = bool
  }
variable "pam" { 
  default = false
  type = bool
  }
variable "sacct_limits" { 
  default = false
  type = bool
  }

variable "unsupported" {
  type    = bool
  default = false
}

variable "queue" { 
  default = "compute"
  type = string
  }
variable "unsupported_controller" {
  type    = bool
  default = false
}
variable "use_marketplace_image_controller" {
  type    = bool
  default = true
}
variable "unsupported_login" {
  type    = bool
  default = false
}
variable "unsupported_monitoring" {
  type    = bool
  default = false
}
variable "controller_username" {
  type    = string
  default = "opc"
}

variable "compute_username" {
  type    = string
  default = "opc"
}
variable "login_username" {
  type    = string
  default = "opc"
}
variable "monitoring_username" {
  type    = string
  default = "opc"
}
variable "autoscaling_monitoring" {
  type    = bool
  default = false
}

variable "autoscaling_mysql_service" {
  type    = bool
  default = false
}

variable "monitoring_shape_name" {
  type    = string
  default = "MySQL.VM.Standard.E3.1.16GB"
}

variable "admin_username" {
  type    = string
  default = "admin"
}

variable "admin_password" {
  type    = string
  default = "Monitor1234!"
}

variable "scratch_nfs_mount" { 
  default = ""
  type = string
  }
variable "scratch_nfs_export" { 
 
  default = ""
  type = string
  }
variable "cluster_nfs_mount" { 
  default = "" 
  type = string
  }
variable "cluster_nfs_export" { 
  default = ""
  type = string
  }

variable "private_deployment" { 
  default = false
  type = bool
  }

variable "localdisk" { 
  default = true 
  type = bool
  }
variable "log_vol" { 
  default = false
  type = bool
  }
variable "redundancy" { 
  default = true
  type = bool
  }

variable "use_marketplace_image_login" { 
  default = true
  type = bool
  }
variable "use_marketplace_image_monitoring" { 
  default = true
  type = bool
  }

variable "marketplace_listing_login" {
  default = "HPC_OL8"
  type = string
}
variable "marketplace_listing_monitoring" {
  default = "HPC_OL8"
  type = string
}
variable "marketplace_listing_controller" {
  default = "HPC_OL8"
  type = string
}
variable "zone_name" {
  default = ""
  type = string
}
variable "dns_entries" {
  default = true
  type = bool
}
variable "healthchecks" {
  default = true
  type = bool
}
variable "BIOS" {
  default = false
  type = bool
}
variable "IOMMU" {
  default = false
  type = bool
}
variable "SMT" {
  default = true
  type = bool
}
variable "virt_instr" {
  default = false
  type = bool
}
variable "access_ctrl" {
  default = false
  type = bool
}
variable "numa_nodes_per_socket" {
  default = "Default"
  type = string
}
variable "percentage_of_cores_enabled" {
  default = "Default"
  type = string
}
variable "change_hostname" {
  default = false
  type = bool
}
variable "hostname_convention" {
  default = "GPU"
  type = string
}
