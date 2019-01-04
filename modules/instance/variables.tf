
variable "compartment_ocid" {}
variable "instances" {}
variable "ad" {}
variable "name" {}
variable "cluster_name" { default = "cluster" }
variable "shape" {}
variable "volumes" { default = 0 }
variable "volume_size" { default = "50"}
variable "public_ip" { default = true }

variable "ssh_key" {}
variable "bootstrap" { default = "" }
variable "subnet_id" {}
variable "source_type" { default = "image" }
variable "source_id" { }
variable "attachment_type" { default = "ISCSI" }