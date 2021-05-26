variable "marketplace_source_images" {
  type = map(object({
    ocid = string
    is_pricing_associated = bool
    compatible_shapes = set(string)
  }))
  default = {
    main_mktpl_image = {
      ocid = "ocid1.image.oc1..aaaaaaaa5yxem7wzie34hi5km4qm2t754tsfxrjuefyjivebrxjad4jcj5oa"
      is_pricing_associated = false
      compatible_shapes = []
    }
    supporting_image = {
      ocid = "ocid1.image.oc1..aaaaaaaazeefig7dqaoheiyoufmllolc3tuiv2c4xueecpr33dm3k4xjip3a"
      is_pricing_associated = false
      compatible_shapes = []
    }
  }
}
