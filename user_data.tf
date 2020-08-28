data "template_file" "bastion_config" {
  template = file("config.bastion")
  vars = {
    key = tls_private_key.ssh.private_key_pem
  }
}

data "template_file" "config" {
  template = file("config.hpc")
}


