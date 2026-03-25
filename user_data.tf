locals {
  controller_config = templatefile("config.controller", {
    key = tls_private_key.ssh.private_key_pem
  })
  
  config = templatefile("config.hpc", {})
}


