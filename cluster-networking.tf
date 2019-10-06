resource "oci_core_cluster_network" "cluster_network" {
    depends_on = ["oci_core_app_catalog_subscription.mp_image_subscription"]
    compartment_id = "${var.compartment_ocid}"
    instance_pools {
        instance_configuration_id = "${oci_core_instance_configuration.instance_configuration.id}"
        size = "${var.node_count}"
        display_name = "${local.cluster_name}"
    }
    placement_configuration {
        availability_domain = "${var.ad}"
        primary_subnet_id = "${var.private == true ? oci_core_subnet.private-subnet.id : oci_core_subnet.public-subnet.id}"
    }

    display_name = "${local.cluster_name}"
}

