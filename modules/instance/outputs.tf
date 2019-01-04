output "instance_id" {
    value = "${oci_core_instance.instance.*.id}"
}

output "volume_id" { 
    value = "${oci_core_volume.volume.*.id}"
}

output "attachment_id" { 
    value = "${oci_core_volume_attachment.attachment.*.id}"
}

output "public_ip" { 
    value = "${oci_core_instance.instance.*.public_ip}"
}

output "private_ip" { 
    value = "${oci_core_instance.instance.*.private_ip}"
}

output "instance_name" { 
    value = [
        "${oci_core_instance.instance.*.display_name}"
    ]
}