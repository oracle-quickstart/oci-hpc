data "oci_identity_domains" "default" {
  count          = local.lookup_default_identity_domain ? 1 : 0
  compartment_id = var.tenancy_ocid
  display_name   = "Default"
  type           = "DEFAULT"
  state          = "ACTIVE"
}

data "oci_identity_dynamic_groups" "existing" {
  provider       = oci.home
  count          = var.create_policies && local.existing_dynamic_group_id != null && var.use_default_identity_domain ? 1 : 0
  compartment_id = var.tenancy_ocid
}

data "oci_identity_domains_dynamic_resource_groups" "existing" {
  count                         = var.create_policies && local.existing_dynamic_group_id != null && !var.use_default_identity_domain ? 1 : 0
  idcs_endpoint                 = local.idcs_endpoint
  dynamic_resource_group_filter = format("ocid eq \"%s\"", local.existing_dynamic_group_id)
}

locals {
  existing_dynamic_groups        = coalesce(one(data.oci_identity_dynamic_groups.existing[*].dynamic_groups), [])
  existing_domain_dynamic_groups = coalesce(one(data.oci_identity_domains_dynamic_resource_groups.existing[*].dynamic_resource_groups), [])

  identity_domain_name = try(coalesce(
    try(one(data.oci_identity_domains.default[0].domains[*].display_name), null),
    try(data.oci_identity_domain.selected[0].display_name, null),
  ), null)
  idcs_endpoint = try(coalesce(
    try(one(data.oci_identity_domains.default[0].domains[*].url), null),
    try(data.oci_identity_domain.selected[0].url, null),
  ), null)

  use_identity_domain_dynamic_group = local.should_create_dynamic_group && local.idcs_endpoint != null
  existing_dynamic_group_name = try(coalesce(
    try(one([for group in local.existing_dynamic_groups : group.name if group.id == local.existing_dynamic_group_id]), null),
    try(one([for group in local.existing_domain_dynamic_groups : group.display_name if group.ocid == local.existing_dynamic_group_id]), null),
  ), null)
  dynamic_group_name = coalesce(local.existing_dynamic_group_name, format("slurm-%s-dg", local.cluster_name))
  policy_group_ref = local.idcs_endpoint != null ? (
    format("'%s'/'%s'", local.identity_domain_name, local.dynamic_group_name)
    ) : (
    local.dynamic_group_name
  )

  network_rule_templates = [
    "Allow dynamic-group %s to use virtual-network-family in compartment id %s",
    "Allow dynamic-group %s to manage dns in compartment id %s",
  ]

  target_rule_templates = concat(
    [
      "Allow dynamic-group %s to manage compute-management-family in compartment id %s",
      "Allow dynamic-group %s to manage instance-family in compartment id %s",
      "Allow dynamic-group %s to manage volume-family in compartment id %s",
      "Allow dynamic-group %s to manage queues in compartment id %s",
      "Allow dynamic-group %s to use queue-push in compartment id %s",
      "Allow dynamic-group %s to use queue-pull in compartment id %s",
      "Allow dynamic-group %s to use functions-family in compartment id %s",
    ],
    local.separate_network_policy ? [] : local.network_rule_templates,
    var.alerting ? [
      "Allow dynamic-group %s to use ons-family in compartment id %s",
    ] : [],
    var.cluster_monitoring && !var.ingest_oci_metrics ? [
      "Allow dynamic-group %s to read metrics in compartment id %s",
      "Allow dynamic-group %s to read file-family in compartment id %s",
    ] : [],
    var.ingest_oci_metrics ? [
      "Allow dynamic-group %s to read all-resources in compartment id %s",
      "Allow dynamic-group %s to use stream-family in compartment id %s",
    ] : [],
    local.gpu_memory_shape ? [
      "Allow dynamic-group %s to manage compute-clusters in compartment id %s",
      "Allow dynamic-group %s to manage compute-gpu-memory-clusters in compartment id %s",
    ] : []
  )

  target_policy_statements = [
    for rule in local.target_rule_templates : format(rule, local.policy_group_ref, var.targetCompartment)
  ]

  network_policy_statements = [
    for rule in local.network_rule_templates : format(rule, local.policy_group_ref, local.network_compartment_id)
  ]

  tenancy_dynamic_group_rule_templates = concat(
    [
      "Allow dynamic-group %s to read app-catalog-listing in tenancy",
      "Allow dynamic-group %s to use tag-namespaces in tenancy",
      "Allow dynamic-group %s to manage compute-bare-metal-hosts in tenancy",
    ],
    local.gpu_memory_shape ? [
      "Allow dynamic-group %s to read compute-gpu-memory-fabrics in tenancy",
    ] : []
  )

  tenancy_policy_statements = concat(
    [for rule in local.tenancy_dynamic_group_rule_templates : format(rule, local.policy_group_ref)],
    var.ingest_oci_metrics ? [
      "Allow any-user to read metrics in tenancy where all {request.principal.type = 'serviceconnector', request.principal.compartment.id = '${var.targetCompartment}'}",
      "Allow any-user to use stream-push in compartment id ${var.targetCompartment} where all {request.principal.type='serviceconnector', request.principal.compartment.id='${var.targetCompartment}'}",
    ] : [],
    var.add_lfs && var.create_lfs == "new" ? [
      "Allow service lustrefs to use virtual-network-family in tenancy",
    ] : [],
    local.gpu_memory_shape ? [
      "Allow any-user to use compute-hpc-islands in tenancy",
      "Allow any-user to use compute-network-blocks in tenancy",
      "Allow any-user to use compute-local-blocks in tenancy",
      "Allow any-user to use compute-bare-metal-hosts in tenancy",
      "Allow any-user to use compute-gpu-memory-fabrics in tenancy",
    ] : []
  )
}

resource "null_resource" "slurm_iam_option_validation" {
  count = var.create_policies ? 1 : 0

  lifecycle {
    precondition {
      condition = (
        local.should_create_dynamic_group ||
        local.existing_dynamic_group_id != null
      )
      error_message = "Create Policies requires a dynamic group OCID when Use existing Dynamic Group is selected."
    }

    precondition {
      condition = (
        local.existing_dynamic_group_id == null ||
        local.existing_dynamic_group_name != null
      )
      error_message = "The existing dynamic group OCID could not be resolved in the selected identity domain."
    }
  }
}

resource "oci_identity_dynamic_group" "slurm" {
  provider       = oci.home
  count          = local.should_create_dynamic_group && !local.use_identity_domain_dynamic_group ? 1 : 0
  compartment_id = var.tenancy_ocid
  name           = local.dynamic_group_name
  description    = format("Dynamic group for Slurm stack %s", local.cluster_name)
  matching_rule  = local.principal_matching_rule

  lifecycle {
    ignore_changes = [defined_tags]
  }
}

resource "oci_identity_domains_dynamic_resource_group" "slurm" {
  count         = local.should_create_dynamic_group && local.use_identity_domain_dynamic_group ? 1 : 0
  idcs_endpoint = local.idcs_endpoint
  display_name  = local.dynamic_group_name
  description   = format("Dynamic group for Slurm stack %s", local.cluster_name)
  matching_rule = local.principal_matching_rule
  schemas       = ["urn:ietf:params:scim:schemas:oracle:idcs:DynamicResourceGroup"]
}

resource "oci_identity_policy" "slurm_runtime" {
  provider       = oci.home
  count          = var.create_policies ? 1 : 0
  depends_on     = [null_resource.slurm_iam_option_validation, oci_identity_dynamic_group.slurm, oci_identity_domains_dynamic_resource_group.slurm]
  compartment_id = var.targetCompartment
  name           = format("slurm-%s-runtime-policy", local.cluster_name)
  description    = format("Runtime policies for Slurm stack %s", local.cluster_name)
  statements     = local.target_policy_statements

  lifecycle {
    ignore_changes = [defined_tags]
  }
}

resource "oci_identity_policy" "slurm_network" {
  provider       = oci.home
  count          = var.create_policies && local.separate_network_policy ? 1 : 0
  depends_on     = [null_resource.slurm_iam_option_validation, oci_identity_dynamic_group.slurm, oci_identity_domains_dynamic_resource_group.slurm]
  compartment_id = local.network_compartment_id
  name           = format("slurm-%s-network-policy", local.cluster_name)
  description    = format("Network and DNS policies for Slurm stack %s", local.cluster_name)
  statements     = local.network_policy_statements

  lifecycle {
    ignore_changes = [defined_tags]
  }
}

resource "oci_identity_policy" "slurm_tenancy" {
  provider       = oci.home
  count          = var.create_policies ? 1 : 0
  depends_on     = [null_resource.slurm_iam_option_validation, oci_identity_dynamic_group.slurm, oci_identity_domains_dynamic_resource_group.slurm]
  compartment_id = var.tenancy_ocid
  name           = format("slurm-%s-tenancy-policy", local.cluster_name)
  description    = format("Tenancy-scope policies for Slurm stack %s", local.cluster_name)
  statements     = local.tenancy_policy_statements

  lifecycle {
    ignore_changes = [defined_tags]
  }
}
