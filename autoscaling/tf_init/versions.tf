terraform {
  required_version = ">= 1.2"
  required_providers {
     oci = {
         source = "oracle/oci"
         version = "7.1.0"
     }
  }
}