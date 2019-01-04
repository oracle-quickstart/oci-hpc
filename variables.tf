variable "ad" { default = "2" } // Availability domain 
variable "network_cidr" { default = "10.254.0.0/16" }
variable "headnode_shape" { default = "VM.Standard2.8" } // Shape used for headnode server
variable "compute_shape" { 	default = "VM.Standard2.8" } // Shape used by compute workers
variable "gluster_shape" { default = "VM.DenseIO1.8"} // Shape used by gluster workers
variable "gluster_count" { default = "3" } // Number of gluster nodes 
variable "compute_count" { default = "2" } // Number of compute nodes
variable "headnode_volumes" { default = "0" }
variable "headnode_volume_size" { default = "1024" }
variable "compute_volumes" { default = "0" }
variable "compute_volume_size" { default = "1024" }
variable "gluster_volumes" { default = "0" } // Block Volumes to attach for gluster node 
variable "gluster_volume_size" { default = "1024" } // Block volume size
variable "image" { 
	type = "map" 
	default = { 
		us-phoenix-1 	= "ocid1.image.oc1.phx.aaaaaaaaoqj42sokaoh42l76wsyhn3k2beuntrh5maj3gmgmzeyr55zzrwwa"
		us-ashburn-1 	= "ocid1.image.oc1.iad.aaaaaaaageeenzyuxgia726xur4ztaoxbxyjlxogdhreu3ngfj2gji3bayda"
		eu-frankfurt-1 	= "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaaitzn6tdyjer7jl34h2ujz74jwy5nkbukbh55ekp6oyzwrtfa4zma"
		uk-london-1		= "ocid1.image.oc1.uk-london-1.aaaaaaaa32voyikkkzfxyo4xbdmadc2dmvorfxxgdhpnk6dw64fa3l4jh7wa"
	}
}
