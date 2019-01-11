variable "ad" { default = "3" } // Availability domain 
variable "additional_headnode_roles" { 
	default = ["intelmpi", "pbspro_server", "gluster"]
}

variable "additional_worker_roles" { 
	default = ["intelmpi", "pbspro_execution", "gluster"]
}
// Currently gluster. Potentialy other types of storage. 
variable "storage_role" { default = ["storage", "gluster"] } 

variable "additional_storage_roles" { 
	default = []
}
variable "additional_role_all" { 
	default = []
}
variable "network_cidr" { default = "10.254.0.0/16" }
variable "headnode_shape" { default = "VM.Standard2.8" } // Shape used for headnode server
variable "compute_shape" { default = "BM.HPC2.36" } // Shape used by compute workers
variable "storage_shape" { default = "VM.DenseIO1.8"} // Shape used by gluster workers
variable "storage_count" { default = "3" } // Number of gluster nodes 
variable "compute_count" { default = "2" } // Number of compute nodes
variable "headnode_volumes" { default = "1" }
variable "headnode_volume_size" { default = "1024" }
variable "compute_volumes" { default = "0" }
variable "compute_volume_size" { default = "1024" }
variable "storage_volumes" { default = "0" } // Block Volumes to attach for gluster node 
variable "storage_volume_size" { default = "1024" } // Block volume size
variable "image" { 
	type = "map" 
	default = { 
		us-phoenix-1 	= "ocid1.image.oc1.phx.aaaaaaaaoqj42sokaoh42l76wsyhn3k2beuntrh5maj3gmgmzeyr55zzrwwa"
		us-ashburn-1 	= "ocid1.image.oc1.iad.aaaaaaaageeenzyuxgia726xur4ztaoxbxyjlxogdhreu3ngfj2gji3bayda"
		eu-frankfurt-1 	= "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaaitzn6tdyjer7jl34h2ujz74jwy5nkbukbh55ekp6oyzwrtfa4zma"
		uk-london-1		= "ocid1.image.oc1.uk-london-1.aaaaaaaa32voyikkkzfxyo4xbdmadc2dmvorfxxgdhpnk6dw64fa3l4jh7wa"
	}
}
