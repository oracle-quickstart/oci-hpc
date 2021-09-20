resource "oci_identity_policy" "clusters_policy" {
    count = var.create_iam ? 1 : 0
    compartment_id = var.tenancy_ocid
    description = "Policy for cluster ${local.cluster_name}"
    name = "cluster-policy-${local.cluster_name}"
    statements = [ 
        "allow service compute_management to use tag-namespace in tenancy",
        "allow service compute_management to manage compute-management-family in tenancy",
        "allow service compute_management to read app-catalog-listing in tenancy"
    ]
}

resource "oci_identity_policy" "cluster_policy" {
    count = var.create_dynamic_group ? 1 : 0
    compartment_id = var.tenancy_ocid
    description = "Policy for cluster ${local.cluster_name}"
    name = "cluster-policy-${local.cluster_name}"
    statements = [ 
        "Allow dynamic-group ${local.dynamic_group_name} to manage app-catalog-listing in tenancy",
        "Allow dynamic-group ${local.dynamic_group_name} to use tag-namespace in tenancy",
        "Allow dynamic-group ${local.dynamic_group_name} to manage compute-management-family in compartment id ${var.targetCompartment}",
        "Allow dynamic-group ${local.dynamic_group_name} to manage instance-family in compartment id ${var.targetCompartment}",
        "Allow dynamic-group ${local.dynamic_group_name} to manage volume-family in compartment id ${var.targetCompartment}",
        "Allow dynamic-group ${local.dynamic_group_name} to use virtual-network-family in compartment id ${var.vcn_compartment}"

    ]
}

resource "oci_identity_dynamic_group" "cluster_group" {
    count = var.create_dynamic_group ? 1 : 0
    compartment_id = var.tenancy_ocid
    description = "Dynamic group for cluster ${local.cluster_name}"
    name = local.dynamic_group_name
    matching_rule = "Any { instance.id = '${oci_core_instance.bastion.id}' }"
}
