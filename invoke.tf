resource "null_resource" "invoke_and_assert" {
  count = var.prechecks ? 1 : 0
  depends_on = [
    oci_functions_function.function,
    oci_core_instance.controller,
    data.oci_dns_zones.dns_zones,
    oci_identity_policy.slurm_runtime,
    oci_identity_policy.slurm_network,
    oci_identity_policy.slurm_tenancy
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
      # Retry for up to approximately 10 minutes while IAM policies propagate.
      MAX_ATTEMPTS=${var.create_policies ? 12 : 1}
      ATTEMPT=1
      RETRY_DELAY=15

      while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do
        echo "Preflight attempt $ATTEMPT of $MAX_ATTEMPTS..."

        if RESULT=$(OCI_CLI_REGION=${var.region} oci $AUTH_FLAG fn function invoke \
          --function-id ${oci_functions_function.function.id} \
          --file "-" \
          --body "$JSON_BODY" \
        ); then
          :
        elif RESULT=$(OCI_CLI_REGION=${var.region} oci fn function invoke \
          --function-id ${oci_functions_function.function.id} \
          --file "-" \
          --body "$JSON_BODY" \
        ); then
          :
        else
          RESULT='{"status":"FAIL","checks":{"function_invoke":"FAIL"}}'
        fi

        echo "Result: $RESULT"
        echo "$RESULT" > /tmp/preflight_result.json
        STATUS=$(echo "$RESULT" | jq -r '.status // "FAIL"' 2>/dev/null || echo "FAIL")

        if [ "$STATUS" = "PASS" ]; then
          break
        fi

        echo "Preflight permissions are not ready yet."
        echo "$RESULT" | jq '.checks' 2>/dev/null || true

        if [ "$ATTEMPT" -eq "$MAX_ATTEMPTS" ]; then
          echo "PREFLIGHT FAILED after $MAX_ATTEMPTS attempts."
          exit 1
        fi

        echo "Retrying in $RETRY_DELAY seconds..."
        sleep "$RETRY_DELAY"
        ATTEMPT=$((ATTEMPT + 1))
        RETRY_DELAY=$((RETRY_DELAY * 2))
        if [ "$RETRY_DELAY" -gt 60 ]; then
          RETRY_DELAY=60
        fi
      done

      echo "PREFLIGHT PASSED - all permissions verified"
    EOT
  }
}
