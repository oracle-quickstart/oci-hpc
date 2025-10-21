locals {
  invalid_ha_config = !var.create_fss && var.slurm_ha
}

resource "null_resource" "validate_ha_setup" {
  count = local.invalid_ha_config ? 1 : 0

  lifecycle {
    precondition {
      condition     = !local.invalid_ha_config
      error_message = "Error: Slurm HA configuration requires a shared FSS (create_fss = true). "
    }
  }
}