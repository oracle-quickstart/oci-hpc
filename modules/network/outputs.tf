output "public-subnet-1-id" {
  value = "${oci_core_subnet.public-subnet-1.id}"
}

output "private-subnet-1-id" {
  value = "${oci_core_subnet.private-subnet-1.id}"
}

output "public-subnet-1-ip" {
  value = "${oci_core_subnet.public-subnet-1.cidr_block}"
}

output "private-subnet-1-ip" {
  value = "${oci_core_subnet.private-subnet-1.cidr_block}"
}

output "vcn-cidr" { 
    value = "${oci_core_vcn.vcn.cidr_block}"
}

output "vcn-id" { 
    value = "${oci_core_vcn.vcn.id}"
}

output "vcn-dns" { 
    value = "${oci_core_vcn.vcn.dns_label}"
}

output "public-subnet-1-dns" { 
    value = "${oci_core_subnet.public-subnet-1.dns_label}"
}

output "private-subnet-1-dns" { 
    value = "${oci_core_subnet.private-subnet-1.dns_label}"
}