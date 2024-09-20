terraform {
  required_version = ">= 1.2"
  required_providers {
     oci = {
         source = "oracle/oci"
         version = ">= 6.9.0"
     }
     local = { 
           source = "hashicorp/local"
           version = ">= 2.1.0"
     }
     tls = {
           source = "hashicorp/tls"
           version = ">= 3.0.0"
     }
     random = {
           source = "hashicorp/random"
           version = ">= 3.0.0"
     }
  }
}