variable "tenancy_ocid" {
}

#variable "user_ocid" {
#}
variable "region" {
}

#variable "private_key_path" {
#}
#variable "fingerprint" {
#}
variable "image" {
  default = "ocid1.image.oc1..aaaaaaaafgzcla4pkskkegec3okzhbtmaylnldbxoa4ln7d6npytnqwu3mca"
}

variable "shape" {
  default = "BM.HPC2.36"
}

variable "ad" {
}

variable "ssh_key" {
}

variable "compartment_ocid" {
}

variable "vcn_subnet" {
  default = "172.16.0.0/23"
}

variable "public_subnet" {
  default = "172.16.0.0/24"
}

variable "private_subnet" {
  default = "172.16.1.0/24"
}

variable "private" {
  default = true
}

variable "node_count" {
}

variable "bastion_shape" {
  default = "VM.Standard2.1"
}

variable "bastion_image" {
  type = map(string)
  default = {
    "ap-mumbai-1"    = "ocid1.image.oc1.ap-mumbai-1.aaaaaaaanqnm77gq2dpmc2aih2ddlwlahuv2qwmokufb7zbi52v67pzkzycq"
    "ap-seoul-1"     = "ocid1.image.oc1.ap-seoul-1.aaaaaaaav3lc5w7cvz5yr6hpjdubxupjeduzd5xvaroyhjg6vwqzsdvgus6q"
    "ap-sydney-1"    = "ocid1.image.oc1.ap-sydney-1.aaaaaaaagtfumjxhosxrkgfci3dgwvsmp35ip5nbhy2rypxfh3rwtqsozkcq"
    "ap-tokyo-1"     = "ocid1.image.oc1.ap-tokyo-1.aaaaaaaajousbvplzyrh727e3d4sb6bam5d2fomwhbtzatoun5sqcuvvfjnq"
    "ca-toronto-1"   = "ocid1.image.oc1.ca-toronto-1.aaaaaaaavr35ze44lkflxffkhmt4xyamkfjpbjhsm5awxjwlnp3gpx7h7fgq"
    "eu-frankfurt-1" = "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaa7gj6uot6tz6t34qjzvkldxtwse7gr5m7xvnh6xfm53ddxp3w37ja"
    "eu-zurich-1"    = "ocid1.image.oc1.eu-zurich-1.aaaaaaaasl3mlhvgzhfglqqkwdbppmmgomkz6iyi42wjkceldqcpecg7jzgq"
    "sa-saopaulo-1"  = "ocid1.image.oc1.sa-saopaulo-1.aaaaaaaawamujpmwxbjgrfeb66zpew5sgz4bimzb4wgcwhqdjyct53bucvoq"
    "uk-london-1"    = "ocid1.image.oc1.uk-london-1.aaaaaaaa6trfxqtp5ib7yfgj725js3o6agntmv6vckarebsmacrhdxqojeya"
    "us-ashburn-1"   = "ocid1.image.oc1.iad.aaaaaaaayuihpsm2nfkxztdkottbjtfjqhgod7hfuirt2rqlewxrmdlgg75q"
    "us-langley-1"   = "ocid1.image.oc2.us-langley-1.aaaaaaaaazlspcasnl4ibjwu7g5ukiaqjp6xcbk5lqgtdsazd7v6evbkwxcq"
    "us-luke-1"      = "ocid1.image.oc2.us-luke-1.aaaaaaaa73qnm5jktrwmkutf6iaigib4msieymk2s5r5iweq5yvqublgcx5q"
    "us-phoenix-1"   = "ocid1.image.oc1.phx.aaaaaaaadtmpmfm77czi5ghi5zh7uvkguu6dsecsg7kuo3eigc5663und4za"
  }
}

variable "use_marketplace_image" {
  default = 1
}

variable "use_existing_vcn" {
  default = 0
}

variable "vcn_id" {
  default = ""
}

variable "bastion_subnet_id" {
  default = ""
}

variable "cluster_subnet_id" {
  default = ""
}

