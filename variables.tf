variable "region" {}
variable "tenancy_ocid" {} 
variable "targetCompartment" {} 
variable "ad" {}
variable "ssh_key" {}
variable "cluster_network" { default = true } 
variable "use_custom_name" {}
variable "cluster_name" { default = "" }
variable "bastion_ad" {}
variable "bastion_shape" {}
variable "use_standard_image" {}
variable "custom_bastion_image" {}
variable "bastion_boot_volume_size" {}
variable "cluster_network_shape" { default = "BM.HPC2.36" }
variable "instance_pool_shape" { default = "VM.Standard2.4" }
variable "node_count" {}
variable "boot_volume_size" {}
variable "use_marketplace_image" {}
variable "image" { default = "ocid1.image.oc1..aaaaaaaa5yxem7wzie34hi5km4qm2t754tsfxrjuefyjivebrxjad4jcj5oa" }
variable "use_cluster_nfs" { default = true}
variable "use_scratch_nfs" { default = true }
variable "cluster_nfs_path" { default = "/nfs/cluster" } 
variable "scratch_nfs_path" { default = "/nfs/scratch" } 
variable "vcn_compartment" { default = ""}
variable "vcn_id" { default = ""}
variable "use_existing_vcn" {}
variable "public_subnet_id" { default = ""}
variable "private_subnet_id" { default = ""}
variable "vcn_subnet" {}
variable "public_subnet" {}
variable "additional_subnet" {}
variable "private_subnet" {}
variable "ssh_cidr" {}
variable "slurm" { default = false}
