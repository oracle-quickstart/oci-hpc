resource "null_resource" "invoke_and_assert" {
  count = var.prechecks ? 1 : 0
  depends_on = [
    oci_functions_function.function,
    oci_core_instance.controller,
    data.oci_dns_zones.dns_zones
  ]

  provisioner "local-exec" {
    command = <<EOT
      set -e
      echo "Invoking preflight checker function..."

      JSON_BODY=$(jq -n \
        --arg cid "${var.targetCompartment}" \
        --arg zid "${data.oci_dns_zones.dns_zones.zones[0].id}" \
        --arg zname "${local.zone_name}" \
        --arg iid "${oci_core_instance.controller.id}" \
        --arg qid "${local.queue_ocid}" \
        '{action:"preflight", COMPARTMENT_ID:$cid, ZONE_ID:$zid, ZONE_NAME:$zname, INSTANCE_ID:$iid, QUEUE_ID:$qid}')

      # Try instance principal first; fall back to default config if unavailable
      AUTH_FLAG="--auth instance_principal"
      RESULT=$(OCI_CLI_REGION=${var.region} oci $AUTH_FLAG fn function invoke \
        --function-id ${oci_functions_function.function.id} \
        --file "-" \
        --body "$JSON_BODY" \
      ) || RESULT=$(oci fn function invoke \
        --function-id ${oci_functions_function.function.id} \
        --file "-" \
        --body "$JSON_BODY" \
      )

      echo "Result: $RESULT"
      echo "$RESULT" > /tmp/preflight_result.json

      STATUS=$(echo "$RESULT" | jq -r '.status // "FAIL"')
      if [ "$STATUS" != "PASS" ]; then
        echo "PREFLIGHT FAILED - check results above"
        echo "$RESULT" | jq '.checks'
        exit 1
      fi
      echo "PREFLIGHT PASSED - all permissions verified"
    EOT
  }
}
