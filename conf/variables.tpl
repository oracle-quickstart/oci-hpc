variable "region" {default = "##REGION##"}
variable "tenancy_ocid" {default = "${tenancy_ocid}"} 
variable "targetCompartment" {default = "##COMP##"} 
variable "ad" {default = "##AD##"}
variable "cluster_network" { default = ##CN##} 
variable "use_custom_name" {default = true}
variable "cluster_name" {default = "##NAME##" }
variable "cluster_network_shape" { default = "##SHAPE##" }
variable "compute_cluster" { default = ##CC## } 
variable "compute_cluster_exists" { default = false }
variable "compute_cluster_id" { default = "" } 
variable "compute_cluster_start_index" { default = 0 } 
variable "instance_pool_shape" { default = "##SHAPE##" }
variable "instance_type" {default = "##INST_TYPE##" }
variable "node_count" { default="##NODES##" }
variable "boot_volume_size" {default = "##BOOT##"}
variable "use_marketplace_image" {  default = "##USEMP##" }
variable "scratch_nfs_path" { default = "${scratch_nfs_path}" } 
variable "use_scratch_nfs" { default = ${use_scratch_nfs} }
variable "cluster_nfs_path" {default = "${cluster_nfs_path}"}
variable "use_cluster_nfs" { default = ${use_cluster_nfs} }
variable "image" { default = "##IMAGE##" }
variable "vcn_compartment" { default = ""}
variable "use_existing_vcn" {default = true}
variable "vcn_subnet" {default = "${vcn_subnet}"}
variable "vcn_id" {default = "${vcn_id}"}
variable "public_subnet_id" { default = "${public_subnet_id}"}
variable "public_subnet" {default = "${public_subnet}"}
variable "private_subnet_id" { default = "##PRIVATE_SUBNET_ID##"}
variable "private_subnet" {default = "##PRIVATE_SUBNET##"}
variable "rdma_subnet" { default = "${rdma_subnet}" }
variable "zone_name" {default = "${zone_name}"}
variable "dns_entries" {default = "${dns_entries}"}
variable "healthchecks" {default = "${healthchecks}"}
variable "slurm" { default = ${slurm} }
variable "rack_aware" { default = ${rack_aware} }
variable "pyxis" { default = ${pyxis} }
variable "pam" { default = ${pam} }
variable "sacct_limits" { default = ${sacct_limits} }
variable "enroot" { default = ${enroot} }
variable "use_compute_agent" { default = ${use_compute_agent} }
variable "slurm_nfs_path" { default = "${slurm_nfs_path}" }
variable "spack" { default = ${spack} }
variable "instance_pool_ocpus" { default = "##OCPU##"}
variable "instance_pool_memory" { default = "##MEM##" }
variable "instance_pool_custom_memory" { default = ##CUSTOM_MEM## }
variable "privilege_sudo" { default = ${privilege_sudo} }
variable "privilege_group_name" { default = "${privilege_group_name}" }
variable "marketplace_listing" {
  default = "##MP_LIST##" 
} 

variable "marketplace_version_id" { 
  type = map(string) 
  default = { 
       "1" = "OL7.9-OFED5.3-1.0.0.1-RHCK-20210607"
       "2" = "OL7.8-OFED5.0-1.0.0.0-UEK-20200826"
       "3" = "OL7.7-OFED-4.4-2.0.7.0-UEK-20200229"
       "4" = "OL7.9-OFED5.0-2.1.8.0-RHCK-20210709"
       "HPC_OL7" = "OracleLinux-7-OCA-RHCK-OFED-23.10-2.1.3.1-2024.03.15-0"
       "HPC_OL8" = "OracleLinux-8-OCA-RHCK-OFED-23.10-2.1.3.1-2024.03.15-0"
       "GPU_OL7_CUDA12.2" = "OracleLinux-7-OCA-RHCK-OFED-23.10-2.1.3.1-GPU-535-CUDA-12.2-2024.03.15-0"
       "GPU_OL8_CUDA12.2" = "OracleLinux-8-OCA-RHCK-OFED-23.10-2.1.3.1-GPU-535-CUDA-12.2-2024.03.15-0"
       "GPU_OL7_CUDA12.4" = "OracleLinux-7-OCA-RHCK-OFED-23.10-2.1.3.1-GPU-535-CUDA-12.4-2024.03.15-0"
       "GPU_OL8_CUDA12.4" = "OracleLinux-8-OCA-RHCK-OFED-23.10-2.1.3.1-GPU-535-CUDA-12.4-2024.03.15-0"
  }
}


# To find the Appcatalog OCID, run 
# oci compute pic listing list --display-name "Oracle Linux 7 - HPC Cluster Networking Image"
variable "old_marketplace_listing_id" {
    default = "ocid1.appcataloglisting.oc1..aaaaaaaahzcnanlki5vonyaeoiajjisejikzczygqqwheifymjqx3ft4iowa"
}
variable "marketplace_listing_id_HPC" {
    default = "ocid1.appcataloglisting.oc1..aaaaaaaahz2xiwfcsbebmqg7sp6lhdt6r2vsjro5jfukkl5cntlqvfhkbzaq"
}
variable "marketplace_listing_id_GPU" {
    default = "ocid1.appcataloglisting.oc1..aaaaaaaab2hkpxsglxfbzitiiqv6djxzj5q5soxotwdem2dd2kbifgk4p55q"
}


variable "controller_block_volume_performance" { 
/* 
  Allowed values 
  "0.  Lower performance"
  "10. Balanced performance"
  "20. High Performance"
*/ 
default = "${controller_block_volume_performance}" 
}

variable "scratch_nfs_type_cluster" { default = "${scratch_nfs_type_cluster}"} 
variable "scratch_nfs_type_pool" { default = "${scratch_nfs_type_pool}" }
variable "controller_name" {default = "${controller_name}"}
variable "controller_ip" {default = "${controller_ip}"}
variable "backup_name" {default = "${backup_name}"}
variable "backup_ip" {default = "${backup_ip}"}
variable "login_name" {default = "${login_name}"}
variable "login_ip" {default = "${login_ip}"}
variable "scripts_folder" {default = "/opt/oci-hpc/bin/"}
variable "autoscaling_folder" {default = "/opt/oci-hpc/autoscaling/"}
variable "cluster_block_volume_size" {default="${cluster_block_volume_size}"}
variable "cluster_block_volume_performance" {default="${cluster_block_volume_performance}"}

variable "ssh_cidr" {default="${ssh_cidr}"}
variable "controller_block" {default = "${controller_block}"}
variable "login_block" {default = "${login_block}"}

variable "controller_mount_ip" {default = "${controller_mount_ip}"}
variable "login_mount_ip" {default = "${login_mount_ip}"}
variable "home_nfs" { default = ${home_nfs} } 
variable "home_fss" { default = ${home_fss} } 
variable "latency_check" { default = ${latency_check} } 
variable "create_fss" { default = ${create_fss} } 
variable "configure" { default = true }

variable "add_nfs" { default = ${add_nfs}}
variable "nfs_target_path" { default = "${nfs_target_path}"}
variable "nfs_source_IP" { default = "${nfs_source_IP}"}
variable "nfs_source_path" { default = "${nfs_source_path}"}
variable "nfs_options" { default = "${nfs_options}"}
variable "queue" { default = "##QUEUE##"}
variable "hyperthreading" { default = ##HT## }

variable "unsupported" { default = ${unsupported} }
variable "image_ocid" { default = "##IMAGE##" }
variable "ldap" { default = ${ldap} }
variable "monitoring" { default = ${monitoring} }
variable "autoscaling_monitoring" { default = ${autoscaling_monitoring} }


variable "tags" { default = "##TAGS##" }
variable "private_deployment" { default = ${private_deployment} }
variable "use_multiple_ads" { default = ${use_multiple_ads} }
variable "controller_username" { default = "${controller_username}" }
variable "compute_username" { default = "${compute_username}" }

variable "localdisk" { default = "${localdisk}" }
variable "log_vol" { default = "${log_vol}" }
variable "redundancy" { default = "${redundancy}" }

variable "instance_pool_ocpus_denseIO_flex" { default = "##OCPU##"}

variable "BIOS" {
  default = ${BIOS}
}
variable "IOMMU" {
  default = ${IOMMU}
}
variable "SMT" {
  default = ${SMT}
}
variable "virt_instr" {
  default = ${virt_instr}
}
variable "access_ctrl" {
  default = ${access_ctrl}
}
variable "numa_nodes_per_socket" {
  default = "${numa_nodes_per_socket}"
}
variable "percentage_of_cores_enabled" {
  default = "${percentage_of_cores_enabled}"
}