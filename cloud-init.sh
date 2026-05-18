#!/bin/bash
#
# First-boot entrypoint for cluster nodes. It reads OCI metadata, mounts the
# shared /config filesystem, and dispatches to the login, monitoring, or
# compute bootstrap script.
#
# Executed on every boot/cloud-init run:
# - detect the OS and default user
# - fetch OCI instance freeform tags and decide the node role
# - configure and mount /config from the shared filesystem
#
# Role-specific bootstrap execution (in order):
# - login nodes run /config/bin/login.sh
# - monitoring nodes run /config/bin/monitoring.sh
# - non-controller compute nodes run /config/bin/compute.sh
source /etc/os-release

# Select the default login user.
if [ "$ID" == "debian" ] || [ "$ID" == "ubuntu" ] ; then
    default_user=ubuntu
else
    default_user=opc
fi

function get_freeform_tag {
    local tag_name="$1"
    curl -fsL --retry 5 --retry-delay 2 -H "Authorization: Bearer Oracle" "http://169.254.169.254/opc/v2/instance/freeformTags/${tag_name}" 2>/dev/null || true
}

# Freeform tags drive which role script this node should execute.
controller_name=$(get_freeform_tag controller_name)
cluster_name=$(get_freeform_tag cluster_name)
login=$(get_freeform_tag login)
monitoring=$(get_freeform_tag monitoring)
controller=$(get_freeform_tag controller)

# The controller owns /config provisioning, so do not make it depend on /config.
if [ "$controller" == "true" ] && [ "$controller_name" == "$(hostname)" ]; then
    echo "Do not run the cloud-init on the controller, this will create a circular dependency on the /config mount"
    exit
fi

role_script=""
if [ "$login" == "true" ]; then
    role_script="/config/bin/login.sh"
elif [ "$monitoring" == "true" ]; then
    role_script="/config/bin/monitoring.sh"
elif [ "$controller" != "true" ] ; then
    role_script="/config/bin/compute.sh"
fi

function bootstrap_files_ready {
    local missing=0
    local required_file

    if [ -z "$role_script" ]; then
        return 0
    fi

    for required_file in \
        "$role_script" \
        /config/bin/common.sh \
        /config/bin/setup_environment.sh \
        /config/bin/setup_os_packages.sh \
        /config/bin/setup_python_packages.sh \
        /config/bin/setup_ansible.sh \
        /config/bin/setup_run_ansible.sh; do
        if [ ! -f "$required_file" ]; then
            echo "$required_file is not present"
            missing=1
        fi
    done
    if [ ! -x "$role_script" ]; then
        echo "$role_script is not executable"
        missing=1
    fi

    return "$missing"
}

# Configure the shared NFS mount used to fetch role-specific bootstrap scripts.
mkdir -p /config

# Remove stale /config entries before adding the expected mount definition.
sed -Ei '/^[[:space:]]*[^#[:space:]]+[[:space:]]+\/config([[:space:]]+|$)/d' /etc/fstab
echo "fss-config:/config /config nfs defaults,nconnect=16 0 0" >> /etc/fstab
systemctl daemon-reload
echo "Configured /config mount in /etc/fstab."

# Mount /config and wait until the controller has populated the expected scripts.
while true; do
    if ! mountpoint -q /config; then
        echo "Attempting to mount /config"
        if ! mount /config; then
            echo "Mount failed. Retrying in 15s..."
            sleep 15
            continue
        fi
    fi

    echo "/config is mounted. Checking if bootstrap files are present"
    if bootstrap_files_ready; then
        echo "/config bootstrap files are present"
        break
    else
        echo "/config bootstrap files are not ready. Retrying in 15s..."
        sleep 15
    fi
done

# Run the selected role script as the image's default non-root user and log output.
function run_role {
    role_command=$1
    su - "$default_user" -c "$role_command" 2>&1 | tee -a /tmp/cloud-init.log
    return ${PIPESTATUS[0]}
}

# Quote the cluster name before embedding it in the su command line.
cluster_name_arg=$(printf '%q' "$cluster_name")

# Dispatch to exactly one role bootstrap script based on metadata tags.
if [ -n "$role_script" ]; then
    run_role "$role_script $cluster_name_arg"
    exit $?
fi
