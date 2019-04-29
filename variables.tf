variable "ad" { default = "3" } // Availability domain 

# Additional role to be added to headnode. This can be for example an application module

variable "additional_headnode_roles" { default = [""] }

# Additional roles to be added to compute nodes. This can be for example an application module.

variable "additional_worker_roles" { default = [""] }

# storage_type variable configures external scratch filesystem  
# that will be mounted on all nodes. 
# This requires storage_count to be greater than 0 and storage_shape to be a DenseIO type instance. 
# current options: 
# 	gluster 	- GlusterFS
# 	beegfs 	- BeeGFS

variable "storage_type" { default = "lustre" }

# Additional roles to be configured on storage nodes
variable "additional_storage_roles" { default = [""] } 
variable "additional_gpu_roles" { default = [""] } 

# Additional role to be added to ALL nodes in the cluster. 
# The value is a LIST type variable And can be set to empty list [""]
# Default value will install openmpi and intelmpi libraries 

variable "additional_role_all" { default = ["intelmpi", "openmpi"] }

variable "network_cidr" { default = "10.254.0.0/16" }

variable "headnode_shape" { default = "VM.Standard2.2" } // Shape used for headnode server
variable "compute_shape" { default = "VM.Standard2.4" } // Shape used by compute workers
variable "storage_shape" { default = "VM.DenseIO2.8"} // Shape used by gluster workers
variable "gpu_shape" { default = "VM.GPU2.1" } 

variable "storage_count" { default = "3" } // Number of gluster nodes 
variable "compute_count" { default = "2" } // Number of compute nodes
variable "gpu_count" { default = "0" } // Number of GPU nodes

variable "headnode_volumes" { default = "1" }
variable "headnode_volume_size" { default = "1024" }
variable "compute_volumes" { default = "0" }
variable "compute_volume_size" { default = "1024" }
variable "storage_volumes" { default = "0" } // Block Volumes to attach for gluster node 
variable "storage_volume_size" { default = "1024" } // Block volume size
variable "gpu_volumes" { default = "0" } // Block Volumes to attach for gluster node 
variable "gpu_volume_size" { default = "1024" } // Block volume size

# Default IMAGE is set to Oracle Linux 7.5 installation
variable "image" { 
	type = "map" 
	default = { 
		us-phoenix-1 	= "ocid1.image.oc1.phx.aaaaaaaacvcy3avanrdb4ida456dgktfhab2phyaikmw75yflugq37eu6oya"
		us-ashburn-1 	= "ocid1.image.oc1.iad.aaaaaaaavzrrzlq2zvj5fd5c27jed7fwou5aqkezxbtmys4aolls54zg7f7q"
		eu-frankfurt-1 	= "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaandary2dpwhw42xgv2d3zsbax2hln4wgcrm2tulo3dg67mwkly6aq"
		uk-london-1	= "ocid1.image.oc1.uk-london-1.aaaaaaaajsuyctwgcvgfkqar2m7znxj25oqwkb7a7tucnrp2adbzoajasspq"
		ca-toronto-1	= "ocid1.image.oc1.ca-toronto-1.aaaaaaaalbg6mthxa6jjmwxb2477px4xb3azu4fl7kubp54s4rrvtswqmo6q"
	}
}

variable "gpu_image" { 
	type = "map" 
	default = { 
		us-phoenix-1 	= "ocid1.image.oc1.phx.aaaaaaaav5wnkbji7ugprtymsxnklfzt2ru77cnvokb2kgcoxsn5zxojipta"
		us-ashburn-1 	= "ocid1.image.oc1.iad.aaaaaaaay66zypxovo6aa4kta5fvv4u5smd5nga7zbcj7iemevtgyvzf4sla"
		eu-frankfurt-1 	= "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaadhty6z7cm22kjqgzcfng33c7ldnfs5p2vhdxkkzm6dweq2tgmfkq"
		uk-london-1	= "ocid1.image.oc1.uk-london-1.aaaaaaaac7bezps4gesb25scxlsan3cqidcv3xpjj22cyy3i3yn6dynuc24a"
		ca-toronto-1	= "ocid1.image.oc1.ca-toronto-1.aaaaaaaa4h37po7vddddjheaxstfsn5irmacrbfzd3kkjs2bwtozigawglea"
	}
}
