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

variable "storage_type" { default = "gluster" }

# Additional roles to be configured on storage nodes
variable "additional_storage_roles" { default = [""] } 

# Additional role to be added to ALL nodes in the cluster. 
# The value is a LIST type variable And can be set to empty list [""]
# Default value will install openmpi and intelmpi libraries 

variable "additional_role_all" { default = ["intelmpi", "openmpi"] }

#
#
#

variable "network_cidr" { default = "10.254.0.0/16" }
variable "headnode_shape" { default = "VM.Standard2.2" } // Shape used for headnode server
variable "compute_shape" { default = "VM.Standard2.4" } // Shape used by compute workers
variable "storage_shape" { default = "VM.DenseIO2.8"} // Shape used by gluster workers
variable "storage_count" { default = "3" } // Number of gluster nodes 
variable "compute_count" { default = "2" } // Number of compute nodes
variable "headnode_volumes" { default = "1" }
variable "headnode_volume_size" { default = "1024" }
variable "compute_volumes" { default = "0" }
variable "compute_volume_size" { default = "1024" }
variable "storage_volumes" { default = "0" } // Block Volumes to attach for gluster node 
variable "storage_volume_size" { default = "1024" } // Block volume size

# Default IMAGE is set to Oracle Linux 7.5 installation
variable "image" { 
	type = "map" 
	default = { 
		us-phoenix-1 	= "ocid1.image.oc1.phx.aaaaaaaadjnj3da72bztpxinmqpih62c2woscbp6l3wjn36by2cvmdhjub6a"
		us-ashburn-1 	= "ocid1.image.oc1.iad.aaaaaaaawufnve5jxze4xf7orejupw5iq3pms6cuadzjc7klojix6vmk42va"
		eu-frankfurt-1 	= "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaagbrvhganmn7awcr7plaaf5vhabmzhx763z5afiitswjwmzh7upna"
		uk-london-1		= "ocid1.image.oc1.uk-london-1.aaaaaaaajwtut4l7fo3cvyraate6erdkyf2wdk5vpk6fp6ycng3dv2y3ymvq"
		ca-toronto-1	= "ocid1.image.oc1.ca-toronto-1.aaaaaaaafozx4cw5fgcnptx6ukgdjjfzvjb2365chtzprratabynb573wria"
	}
}
