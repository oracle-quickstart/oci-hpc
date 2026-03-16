#!/bin/bash
# Usage: ./gather_ldap_data.sh <old_controller_ip>
# Example: ./gather_ldap_data.sh 10.0.0.5

# This script will generate group.list and user.list files containing group and user information from the old cluster.

# Prerequisites:
#   - The remote host must have the 'cluster' command available in the PATH or at /usr/bin/cluster.
#   - SSH key-based authentication must be set up for either 'ubuntu' or 'opc' user on the remote host.


if [ $# -ne 1 ]; then
    echo "Usage: $0 <old_controller_ip>"
    exit 1
fi

OLD_CONTROLLER_IP="$1"

# Auto-detect the remote user by testing connections
echo "Detecting remote user for server $OLD_CONTROLLER_IP..."

if ssh -q -o ConnectTimeout=5 -o BatchMode=yes ubuntu@"$OLD_CONTROLLER_IP" 'exit' 2>/dev/null; then
    REMOTE_USER="ubuntu"
    REMOTE_OS=$(ssh -q ubuntu@"$OLD_CONTROLLER_IP" 'grep "^ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d "\"" || echo "unknown"' 2>/dev/null)
    echo "Successfully connected with ubuntu user (OS: $REMOTE_OS)"
elif ssh -q -o ConnectTimeout=5 -o BatchMode=yes opc@"$OLD_CONTROLLER_IP" 'exit' 2>/dev/null; then
    REMOTE_USER="opc"
    REMOTE_OS=$(ssh -q opc@"$OLD_CONTROLLER_IP" 'grep "^ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d "\"" || echo "unknown"' 2>/dev/null)
    echo "Successfully connected with opc user (OS: $REMOTE_OS)"
else
    echo "Error: Cannot connect to $OLD_CONTROLLER_IP with either ubuntu or opc user"
    echo "Please ensure SSH keys are configured and the user exists"
    exit 1
fi

REMOTE_GROUP_FILE="group.list"
REMOTE_USER_FILE="user.list"
LOCAL_DEST="./"

echo "Connecting to old Slurm controller: $OLD_CONTROLLER_IP ..."

# Run commands on remote controller and generate files
ssh ${REMOTE_USER}@${OLD_CONTROLLER_IP} "bash -s" << 'EOF'
set -e
echo "Generating group and user lists on remote controller..."

if ! command -v cluster >/dev/null 2>&1; then
    if [ -x "/usr/bin/cluster" ]; then
        CLUSTER="/usr/bin/cluster"
    else
        echo "Error: cluster command not found"
        exit 1
    fi
else
    CLUSTER="cluster"
fi

echo "Using cluster command: $CLUSTER"

timeout 5 bash -c '
    [ -f ~/.bashrc ] && source ~/.bashrc 2>/dev/null || true
    [ -f ~/.profile ] && source ~/.profile 2>/dev/null || true
' 2>/dev/null || true

echo "Executing: $CLUSTER group list"
timeout 30 $CLUSTER group list > group.list || {
    echo "Error: Failed to generate group list"
    exit 1
}

echo "Executing: $CLUSTER user list"
timeout 30 $CLUSTER user list > user.list || {
    echo "Error: Failed to generate user list"
    exit 1
}

echo "Files generated successfully:"
wc -l group.list user.list
EOF

if [ $? -ne 0 ]; then
    echo "Error: Failed to generate files on remote server"
    exit 1
fi

echo "Downloading files to local machine..."
scp ${REMOTE_USER}@${OLD_CONTROLLER_IP}:${REMOTE_GROUP_FILE} ${LOCAL_DEST} || exit 1
scp ${REMOTE_USER}@${OLD_CONTROLLER_IP}:${REMOTE_USER_FILE} ${LOCAL_DEST} || exit 1

echo "Files downloaded successfully: ${REMOTE_GROUP_FILE}, ${REMOTE_USER_FILE}"
ls -lh ${LOCAL_DEST}${REMOTE_GROUP_FILE} ${LOCAL_DEST}${REMOTE_USER_FILE}

echo "Cleaning up remote files..."
ssh ${REMOTE_USER}@${OLD_CONTROLLER_IP} "rm -f ${REMOTE_GROUP_FILE} ${REMOTE_USER_FILE}"

echo "LDAP data gathering completed successfully!"

