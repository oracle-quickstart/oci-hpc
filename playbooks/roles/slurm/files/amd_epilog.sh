#!/bin/bash

#
#Copyright (c) Advanced Micro Devices, Inc. All rights reserved.

#Licensed under the Apache License, Version 2.0 (the \"License\");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#Unless required by applicable law or agreed to in writing, software
#distributed under the License is distributed on an \"AS IS\" BASIS,
#WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#See the License for the specific language governing permissions and
#limitations under the License.
#

EXPORT_DIR="/var/run/exporter/"
mod128_array() {
    local arr_str="$1"
    local arr result

    # convert string to array using comma as delimiter
    IFS=',' read -ra arr <<< "$arr_str"

    # modulo 128 to each element
    for i in "${!arr[@]}"; do
        arr[i]=$(( ${arr[i]} % 128 ))
    done

    # join array back into a comma-separated string
    result=$(IFS=','; echo "${arr[*]}")

    echo "$result"
}
AMDGPU_DEVICES=$(mod128_array "${CUDA_VISIBLE_DEVICES}")
AMD_SLURM_GPUS=$(mod128_array "${SLURM_JOB_GPUS}")
MSG=$(
	cat <<EOF
    {
    "SLURM_JOB_ID": "${SLURM_JOB_ID}",
    "SLURM_JOB_USER": "${SLURM_JOB_USER}",
    "SLURM_JOB_PARTITION": "${SLURM_JOB_PARTITION}",
    "SLURM_CLUSTER_NAME": "${SLURM_CLUSTER_NAME}",
    "SLURM_JOB_GPUS": "${AMD_SLURM_GPUS}",
    "CUDA_VISIBLE_DEVICES": "${AMDGPU_DEVICES}",
    "SLURM_SCRIPT_CONTEXT": "${SLURM_SCRIPT_CONTEXT}"
   }
EOF
)
[ -d ${EXPORT_DIR} ] || exit 0
GPUS=$(echo ${AMDGPU_DEVICES} | tr "," "\n")
for GPUID in ${GPUS}; do
	rm -f ${EXPORT_DIR}/${GPUID}
done
