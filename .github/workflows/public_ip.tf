
resource "local_file" "public_ip_controller" {
content  = "${var.controller_username}@${local.host}"
filename = "public_ip.txt"
}
