data "archive_file" "salt-config" {
  depends_on		= ["data.template_file.salt_variables", "local_file.salt_variables"]

  type        = "zip"
  source_dir  = "${path.module}/salt"
  output_path = "${path.module}/conf/salt.zip"
}

data "oci_objectstorage_namespace" "namespace" {
}

resource "oci_objectstorage_bucket" "bucket" {
    depends_on		= ["data.archive_file.salt-config"]
    compartment_id      = "${var.compartment_ocid}"
    name                = "cluster-${local.cluster_name}"
    namespace           = "${data.oci_objectstorage_namespace.namespace.namespace}"
}

resource "oci_objectstorage_object" "salt" {
    depends_on		= ["oci_objectstorage_bucket.bucket", "oci_objectstorage_preauthrequest.salt-par", "data.archive_file.salt-config"]
    #Required
    bucket = "${oci_objectstorage_bucket.bucket.name}"
    source = "${path.module}/conf/salt.zip"
    namespace = "${data.oci_objectstorage_namespace.namespace.namespace}"
    object = "config-${local.cluster_name}.zip"
}

resource "oci_objectstorage_preauthrequest" "salt-par" {
    
    lifecycle { 
        ignore_changes = "*"
    }
    
    #Required
    access_type = "ObjectRead"
    bucket = "${oci_objectstorage_bucket.bucket.name}"
    name = "config-${local.cluster_name}.zip"
    namespace = "${data.oci_objectstorage_namespace.namespace.namespace}"
    time_expires = "${timeadd(timestamp(), "30m")}"

    #Optional
    object = "config-${local.cluster_name}.zip"
}

locals {
  par_url = "https://objectstorage.${var.region}.oraclecloud.com${oci_objectstorage_preauthrequest.salt-par.access_uri}"
}
