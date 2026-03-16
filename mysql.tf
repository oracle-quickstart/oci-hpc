resource "oci_mysql_mysql_db_system" "slurm_mysql" {
  count               = var.slurm_ha ? 1 : 0
	access_mode = "UNRESTRICTED"
	admin_password = var.mysql_admin_password
	admin_username = var.mysql_admin_username
	availability_domain = var.controller_ad
	backup_policy {
		is_enabled = "true"
		pitr_policy {
			is_enabled = "true"
		}
		retention_in_days = "7"
		soft_delete = "ENABLED"
	}
	compartment_id = var.targetCompartment
	crash_recovery = "ENABLED"
	data_storage {
		is_auto_expand_storage_enabled = "true"
		max_storage_size_in_gbs = "32000"
	}
	data_storage_size_in_gb = "1024"
	database_management = "ENABLED"
	database_mode = "READ_WRITE"
	deletion_policy {
		automatic_backup_retention = "DELETE"
		final_backup = "SKIP_FINAL_BACKUP"
		is_delete_protected = "false"
	}
	display_name = "${local.cluster_name}-mysql"
	encrypt_data {
		key_generation_type = "SYSTEM"
	}
	freeform_tags = {
		"cluster_name"    = local.cluster_name
		"controller_name" = oci_core_instance.controller.display_name
	}
	port = "3306"
	port_x = "33060"
	read_endpoint {
		is_enabled = "false"
	}
	secure_connections {
		certificate_generation_type = "SYSTEM"
	} 
	shape_name = var.mysql_shape
	subnet_id = local.subnet_id
}
