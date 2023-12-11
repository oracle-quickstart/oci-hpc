variable "region" {}
variable "tenancy_ocid" {} 
variable "targetCompartment" {} 
variable "ad" {}
variable "secondary_ad" { default = "" }
variable "third_ad" { default = "" }
variable "use_multiple_ads" { default = false }
variable "ssh_key" { }
variable "cluster_network" { default = true } 
variable "compute_cluster" { default = false } 
variable "compute_cluster_exists" { default = false }
variable "compute_cluster_id" { default = "" } 
variable "compute_cluster_start_index" { default = 0 } 
variable "use_custom_name" { default = false }
variable "cluster_name" { default = "" }
variable "bastion_ad" {}
variable "bastion_shape" { default = "VM.Standard2.4" }
variable "bastion_object_storage_par" { default = true }
variable "custom_bastion_image" { 
  type = string
  default = "image.ocid" 
}
variable "custom_login_image" { 
  type = string
  default = "image.ocid" 
}
variable "bastion_boot_volume_size" {}
variable "bastion_boot_volume_backup" {}
variable "bastion_boot_volume_backup_type" {default = "INCREMENTAL"}
variable "bastion_boot_volume_backup_period" {default = "ONE_DAY"}
variable "bastion_boot_volume_backup_retention_seconds" {default = "7776000"}
variable "bastion_boot_volume_backup_time_zone" {default = "REGIONAL_DATA_CENTER_TIME"}
variable "cluster_network_shape" { default = "BM.HPC2.36" }
variable "instance_pool_shape" { default = "VM.Standard2.4" }
variable "node_count" { default = 2 }
variable "boot_volume_size" { default = 50 }
variable "use_marketplace_image" { default = true}
variable "image" { default = "ocid1.image.oc1..aaaaaaaa5yxem7wzie34hi5km4qm2t754tsfxrjuefyjivebrxjad4jcj5oa" }
variable "image_ocid" { default = "ocid1.image.oc1..aaaaaaaa5yxem7wzie34hi5km4qm2t754tsfxrjuefyjivebrxjad4jcj5oa" }
variable "use_compute_agent" { default = false }
variable "unsupported_bastion_image" { default = "" } 
variable "unsupported_login_image" { default = "" } 
variable "use_cluster_nfs" { default = true}
variable "use_scratch_nfs" { default = true }
variable "cluster_nfs_path" { default = "/nfs/cluster" } 
variable "scratch_nfs_path" { default = "/nfs/scratch" } 
variable "vcn_compartment" { default = ""}
variable "vcn_id" { default = ""}
variable "use_existing_vcn" { default = false}
variable "public_subnet_id" { default = ""}
variable "private_subnet_id" { default = ""}
variable "vcn_subnet" { default = "172.16.0.0/21" }
variable "public_subnet" { default = "172.16.0.0/24" }
variable "additional_subnet" { default = "172.16.1.0/24" }
variable "rdma_subnet" { default = "192.168.0.0/16" }
variable "private_subnet" { default = "172.16.4.0/22" }
variable "ssh_cidr" { default = "0.0.0.0/0" }
variable "slurm" { default = false }
variable "slurm_ha" { default = false }
variable "login_node" { default = true }
variable "login_ad" {default = ""}
variable "login_shape" { default = "VM.Standard2.4" }
variable "login_boot_volume_size" {default = 50}
variable "slurm_nfs" { default = false }
variable "rack_aware" { default = false }
variable "ldap" { default = true } 
variable "spack" { default = false } 
variable "bastion_ocpus" { default = 2} 
variable "bastion_ocpus_denseIO_flex" { default = 8} 
variable "instance_pool_ocpus" { default = 2} 
variable "instance_pool_ocpus_denseIO_flex" { default = 8} 
variable "instance_pool_memory" { default = 16 }
variable "instance_pool_custom_memory" { default = false }
variable "login_ocpus" { default = 2} 
variable "login_ocpus_denseIO_flex" { default = 8}
variable "bastion_memory" { default = 16 }
variable "bastion_custom_memory" { default = false }
variable "login_memory" { default = 16 }
variable "login_custom_memory" { default = false }
variable "privilege_sudo" { default = true }
variable "privilege_group_name" { default = "privilege" }


variable "marketplace_listing" { 
  default = "HPC_OL7"
}  
variable "marketplace_version_id" { 
  type = map(string) 
  default = { 
       "1" = "OL7.9-OFED5.3-1.0.0.1-RHCK-20210607"
       "2" = "OL7.8-OFED5.0-1.0.0.0-UEK-20200826"
       "3" = "OL7.7-OFED-4.4-2.0.7.0-UEK-20200229"
       "4" = "OL7.9-OFED5.0-2.1.8.0-RHCK-20210709"
       "HPC_OL7" = "OracleLinux-7-OCA-RHCK-OFED-5.8-3.0.7.0-2023.12.04-1"
       "HPC_OL8" = "OracleLinux-8-OCA-RHCK-OFED-5.8-3.0.7.0-2023.12.04-1"
       "GPU_OL7" = "OracleLinux-7-OCA-RHCK-OFED-5.8-3.0.7.0-GPU-535-2023.12.04-1"
       "GPU_OL8" = "OracleLinux-8-OCA-RHCK-OFED-5.8-3.0.7.0-GPU-535-2023.12.04-1"
  }
}

# To find the Appcatalog OCID, run 
# oci compute pic listing list --display-name "Oracle Linux 7 - HPC Cluster Networking Image"

variable "marketplace_listing_id_HPC" {
    default = "ocid1.appcataloglisting.oc1..aaaaaaaahz2xiwfcsbebmqg7sp6lhdt6r2vsjro5jfukkl5cntlqvfhkbzaq"
}
variable "marketplace_listing_id_GPU" {
    default = "ocid1.appcataloglisting.oc1..aaaaaaaab2hkpxsglxfbzitiiqv6djxzj5q5soxotwdem2dd2kbifgk4p55q"
}
variable "bastion_block_volume_performance" { 
/* 
  Allowed values 
  "0.  Lower performance"
  "10. Balanced performance"
  "20. High Performance"
*/ 

default = "10. Balanced performance" 

}

variable "bastion_block" { 
  default = false
} 

variable "bastion_block_volume_size" { 
  default = 1000
}

variable "login_block_volume_performance" { 
/* 
  Allowed values 
  "0.  Lower performance"
  "10. Balanced performance"
  "20. High Performance"
*/ 

default = "10. Balanced performance" 

}

variable "login_block" { 
  default = false
} 

variable "login_block_volume_size" { 
  default = 1000
}
variable "scratch_nfs_type_cluster" { default = "nvme"} 
variable "scratch_nfs_type_pool" { default = "none" }
variable "cluster_block_volume_size" { default = "1000" }
variable "cluster_block_volume_performance" { default = "10. Balanced performance"}

variable "inst_prin" { default = true}
variable "api_user_key" { default = ""}
variable "api_fingerprint" { default = ""}
variable "api_user_ocid" { default = ""} 
variable "home_nfs" { default = true } 
variable "home_fss" { default = false } 
variable "configure" { default = true }

variable "hyperthreading" { default = true }

variable "autoscaling" { default = false } 
variable "latency_check" { default = true }
variable "add_nfs" { default = false}
variable "create_fss" { default = false }
variable "fss_compartment" {default = ""}
variable "fss_ad" {default = ""}
variable "nfs_target_path" { default = "/app"}
variable "nfs_source_IP" { default = ""}
variable "nfs_source_path" { default = "/app"}
variable "nfs_options" {default = ""}
variable "monitoring" { default = true }
variable "enroot" { default = false }
variable "pyxis" { default = false }
variable "pam" { default = false }
variable "sacct_limits" { default = false }

variable "unsupported" { 
  type=bool
  default = false
} 

variable "queue" {default = "compute"}
variable "unsupported_bastion" { 
  type=bool
  default = false 
}
variable "use_marketplace_image_bastion" { 
  type=bool
  default = true 
}
variable "unsupported_login" { 
  type=bool
  default = false 
}
variable "bastion_username" { 
  type = string 
  default = "opc" 
} 

variable "compute_username" { 
  type = string
  default = "opc" 
} 
variable "login_username" { 
  type = string
  default = "opc" 
} 

variable "autoscaling_monitoring" { 
  type= bool
  default = false
} 

variable "autoscaling_mysql_service" { 
  type= bool
  default = false
} 

variable "monitoring_shape_name" { 
  type = string
  default = "MySQL.VM.Standard.E3.1.16GB"
} 

variable "admin_username" { 
  type = string
  default = "admin"
} 

variable "admin_password" { 
  type = string
  default = "Monitor1234!"
}

variable scratch_nfs_mount { default = ""}
variable scratch_nfs_export {default = ""}
variable cluster_nfs_mount {default = ""}
variable cluster_nfs_export {default = ""}

variable "private_deployment" { default = false }

variable "localdisk" { default = true }
variable "log_vol" { default = false }
variable "redundancy" { default = true }

variable "use_marketplace_image_login" { default = true}

variable "marketplace_listing_login" { 
  default = "HPC_OL7"
} 
variable "marketplace_listing_bastion" { 
  default = "HPC_OL7"
} 
  