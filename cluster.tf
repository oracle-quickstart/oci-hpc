resource "random_pet" "name" {
  length = 2
}

locals {
  cluster_name = var.use_custom_name ? var.cluster_name : random_pet.name.id
}

resource "tls_private_key" "ssh" {
  algorithm = "RSA"
  rsa_bits  = "4096"
}