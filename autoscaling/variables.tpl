variable "region" {default = "${region}"}
variable "tenancy_ocid" {default = "${tenancy_ocid}"} 
variable "targetCompartment" {default = "${targetCompartment}"} 
variable "ad" {default = "${ad}"}
variable "cluster_network" { default = ##CN##} 
variable "use_custom_name" {default = true}
variable "cluster_name" {default = "##NAME##" }
variable "cluster_network_shape" { default = "##SHAPE##" }
variable "instance_pool_shape" { default = "##SHAPE##" }
variable "node_count" { default="##NODES##" }
variable "boot_volume_size" {default = "${boot_volume_size}"}
variable "use_marketplace_image" {  default = "${use_marketplace_image}" }
variable "scratch_nfs_path" { default = "${scratch_nfs_path}" } 
variable "use_scratch_nfs" { default = true }
variable "cluster_nfs_path" {default = "${cluster_nfs_path}"}
variable "use_cluster_nfs" { default = ${use_cluster_nfs} }
variable "image" { default = "${image}" }
variable "vcn_compartment" { default = ""}
variable "use_existing_vcn" {default = true}
variable "vcn_subnet" {default = "${vcn_subnet}"}
variable "public_subnet_id" { default = "${public_subnet_id}"}
variable "public_subnet" {default = "${public_subnet}"}
variable "private_subnet_id" { default = "${private_subnet_id}"}
variable "private_subnet" {default = "${private_subnet}"}
variable "slurm" { default = true }
variable "spack" { default = ${spack} }
variable "instance_pool_ocpus" { default = "##OCPU##"}
variable "instance_pool_memory" { default = ${instance_pool_memory} }
variable "instance_pool_custom_memory" { default = ${instance_pool_custom_memory} }
variable "marketplace_listing" { 
/* 
  Allowed values
   "1. Oracle Linux 7.8 OFED5.0"
   "2. Oracle Linux 7.5 OFED4.4"
*/ 
  default = "${marketplace_listing}" 
} 

variable "marketplace_listing_id" {
  type = map(string)
  default = {
        "1"  =    "ocid1.appcataloglisting.oc1..aaaaaaaahzcnanlki5vonyaeoiajjisejikzczygqqwheifymjqx3ft4iowa"
        "2"  =    "ocid1.appcataloglisting.oc1..aaaaaaaahz2xiwfcsbebmqg7sp6lhdt6r2vsjro5jfukkl5cntlqvfhkbzaq"
  }
}

variable "bastion_block_volume_performance" { 
/* 
  Allowed values 
  "0.  Lower performance"
  "10. Balanced performance"
  "20. High Performance"
*/ 
default = "${bastion_block_volume_performance}" 
}

variable "scratch_nfs_type_cluster" { default = "${scratch_nfs_type_cluster}"} 
variable "scratch_nfs_type_pool" { default = "${scratch_nfs_type_pool}" }
variable "bastion_name" {default = "${bastion_name}"}
variable "bastion_ip" {default = "${bastion_ip}"}
variable "scripts_folder" {default = "/home/opc/autoscaling/"}
variable "cluster_block_volume_size" {default="${cluster_block_volume_size}"}
variable "cluster_block_volume_performance" {default="${cluster_block_volume_performance}"}

variable "ssh_cidr" {default="${ssh_cidr}"}
variable "bastion_block" {default = "${bastion_block}"}

variable "bastion_mount_ip" {default = "${bastion_mount_ip}"}
variable "home_nfs" { default = ${home_nfs} } 
variable "configure" { default = true }

variable "add_nfs" { default = ${add_nfs}}
variable "nfs_target_path" { default = "${nfs_target_path}"}
variable "nfs_source_IP" { default = "${nfs_source_IP}"}
variable "nfs_source_path" { default = "${nfs_source_path}"}
variable "nfs_options" { default = "${nfs_options}"}