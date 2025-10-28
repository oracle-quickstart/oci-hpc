# data "oci_core_image" "controller_validation" {
#     #Required
#     image_id = local.controller_image
# }

# locals {
#   invalid_ha_setup               = !var.create_public_subnets && var.preferred_kubernetes_services == "public"
#   invalid_public_ep              = !var.create_public_subnets && var.control_plane_is_public
#   invalid_bastion                = !var.create_public_subnets && (var.bastion_is_public && var.create_bastion)
#   invalid_worker_rdma_image      = can(regex("(?i)ubuntu", data.oci_core_image.controller_validation))
# }





# resource "null_resource" "validate_controller_username" {
#   count = coalesce(var.custom_controller_image, var.unsupported_controller_image, "none") != "none" ? 1 : 0

#   lifecycle {
#     precondition {
#       condition     = !local.invalid_worker_rdma_image
#       error_message = "Error: Only Ubuntu custom images are supported with GPU & RDMA worker pools. You selected an Ubuntu image: ${data.oci_core_image.worker_rdma[0].display_name}"
#     }
#   }
# }