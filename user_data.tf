data "template_file" "controller_config" {
  template = file("config.controller")
  vars = {
    key = tls_private_key.ssh.private_key_pem
  }
}

data "template_file" "config" {
  template = file("config.hpc")
}


