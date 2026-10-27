#!/bin/bash
# Usage: ./push_ldap_data.sh <new_controller_ip> [--nossh|--ssh]

# This script pushes group.list and user.list files to the new controller, then rebuilds groups and users and assigns users to their groups using the group.list and user.list files.

if [ $# -lt 1 ]; then
    echo "Usage: $0 <new_controller_ip> [--nossh|--ssh]"
    exit 1
fi

NEW_CONTROLLER_IP="$1"
SSH_OPTION="${2:---nossh}"  # Default to --nossh if not provided

# Auto-detect the remote user by testing connections
echo "Detecting remote user for server $NEW_CONTROLLER_IP..."

# Test ubuntu user first
if ssh -q -o ConnectTimeout=5 -o BatchMode=yes ubuntu@"$NEW_CONTROLLER_IP" 'exit' 2>/dev/null; then
    REMOTE_USER="ubuntu"
    # Get OS info for confirmation
    REMOTE_OS=$(ssh -q ubuntu@"$NEW_CONTROLLER_IP" 'grep "^ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d "\"" || echo "unknown"' 2>/dev/null)
    echo "Successfully connected with ubuntu user (OS: $REMOTE_OS)"
# Test opc user if ubuntu fails
elif ssh -q -o ConnectTimeout=5 -o BatchMode=yes opc@"$NEW_CONTROLLER_IP" 'exit' 2>/dev/null; then
    REMOTE_USER="opc"
    # Get OS info for confirmation
    REMOTE_OS=$(ssh -q opc@"$NEW_CONTROLLER_IP" 'grep "^ID=" /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d "\"" || echo "unknown"' 2>/dev/null)
    echo "Successfully connected with opc user (OS: $REMOTE_OS)"
else
    echo "Error: Cannot connect to $NEW_CONTROLLER_IP with either ubuntu or opc user"
    echo "Please ensure:"
    echo "1. SSH key is properly configured"
    echo "2. The correct user exists on the target system"
    echo "3. The server is accessible"
    exit 1
fi

LOCAL_GROUP_FILE="group.list"
LOCAL_USER_FILE="user.list"

echo "Uploading LDAP data files to new Slurm controller: $NEW_CONTROLLER_IP ..."
scp "${LOCAL_GROUP_FILE}" "${REMOTE_USER}@${NEW_CONTROLLER_IP}:~/"
scp "${LOCAL_USER_FILE}" "${REMOTE_USER}@${NEW_CONTROLLER_IP}:~/"

# Pass SSH_OPTION into the remote script explicitly
ssh -q "${REMOTE_USER}@${NEW_CONTROLLER_IP}" "SSH_OPTION='${SSH_OPTION}' bash -s" <<'EOF'
set -e

cd ~ || exit 1

GROUP_FILE="group.list"
USER_FILE="user.list"

# Check if files exist and are readable
if [ ! -r "$GROUP_FILE" ] || [ ! -r "$USER_FILE" ]; then
    echo "Error: Cannot read input files"
    exit 1
fi

# Check if cluster command exists - try multiple approaches
CLUSTER=""
if command -v cluster >/dev/null 2>&1; then
    CLUSTER="cluster"
elif [ -x "/usr/bin/cluster" ]; then
    CLUSTER="/usr/bin/cluster"
else
    echo "Error: cluster command not found"
    exit 1
fi

echo "Using cluster command: $CLUSTER"

# Extract group and user names (handle indented format)
GROUP_NAMES=$(grep -E "^\s*cn:" "$GROUP_FILE" | cut -d: -f2 | tr -d " " | tr '\n' ' ')
USER_NAMES=$(grep -E "^\s*cn:" "$USER_FILE" | cut -d: -f2 | tr -d " " | tr '\n' ' ')

echo "Running group creation logic ..."

# Create arrays for group data
declare -a gnames gids
while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*cn: ]]; then
        gname=$(echo "$line" | cut -d: -f2 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        gnames+=("$gname")
    fi
done < "$GROUP_FILE"

while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*gidNumber: ]]; then
        gid=$(echo "$line" | cut -d: -f2 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        gids+=("$gid")
    fi
done < "$GROUP_FILE"

# Create groups
for ((i=0; i<${#gnames[@]}; i++)); do
    if [ -n "${gnames[i]}" ] && [ -n "${gids[i]}" ]; then
        echo "$CLUSTER group create --gid ${gids[i]} ${gnames[i]}"
        $CLUSTER group create --gid "${gids[i]}" "${gnames[i]}" || echo "Warning: Failed to create group ${gnames[i]}"
    else
        echo "Warning: Empty group name or GID at index $i"
    fi
done

# Cache refresh (with error handling but no timeouts)
sudo sss_cache --groups 2>/dev/null || echo "Warning: sss_cache not available"
sudo systemctl restart sssd 2>/dev/null || echo "Warning: sssd restart failed"

echo "Waiting for all groups to be available..."
for group in $GROUP_NAMES; do
    if [ -n "$group" ]; then
        retries=0
        until getent group "$group" > /dev/null 2>&1; do
            if [ $retries -gt 6 ]; then  # 30 second timeout
                echo "Warning: Group $group not available after 30 seconds"
                break
            fi
            echo "Group $group not yet available, retrying in 5 seconds..."
            sleep 5
            ((retries++))
        done
        if getent group "$group" > /dev/null 2>&1; then
            echo "Group $group exists."
        fi
    fi
done

echo "Group creation phase completed."

echo "Running user creation logic ..."

# Create arrays for user data
declare -a unames dnames user_gids uids
while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*cn: ]]; then
        uname=$(echo "$line" | cut -d: -f2 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        unames+=("$uname")
    fi
done < "$USER_FILE"

while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*displayName: ]]; then
        dname=$(echo "$line" | cut -d: -f2- | sed 's/^[[:space:]]*//')
        dnames+=("$dname")
    fi
done < "$USER_FILE"

while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*gidNumber: ]]; then
        gid=$(echo "$line" | cut -d: -f2 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        user_gids+=("$gid")
    fi
done < "$USER_FILE"

while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*uidNumber: ]]; then
        uid=$(echo "$line" | cut -d: -f2 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        uids+=("$uid")
    fi
done < "$USER_FILE"

# Check if we have uidNumber data, if not, generate UIDs starting from 10000
if [ ${#uids[@]} -eq 0 ] && [ ${#unames[@]} -gt 0 ]; then
    echo "Warning: No uidNumber found in user file, generating UIDs starting from 10000"
    start_uid=10000
    for ((i=0; i<${#unames[@]}; i++)); do
        uids+=($((start_uid + i)))
    done
fi

# Create users
for ((i=0; i<${#unames[@]}; i++)); do
    if [ -n "${unames[i]}" ] && [ -n "${uids[i]}" ] && [ -n "${user_gids[i]}" ]; then
        echo "$CLUSTER user add $SSH_OPTION --gid ${user_gids[i]} --uid ${uids[i]} -n \"${dnames[i]}\" -p ${unames[i]} ${unames[i]}"
        $CLUSTER user add $SSH_OPTION --gid "${user_gids[i]}" --uid "${uids[i]}" -n "${dnames[i]}" -p "${unames[i]}" "${unames[i]}" || echo "Warning: Failed to create user ${unames[i]}"
    else
        echo "Warning: Empty user data at index $i: name='${unames[i]}' uid='${uids[i]}' gid='${user_gids[i]}'"
    fi
done

echo "Verifying users..."
for user in $USER_NAMES; do
    if [ -n "$user" ]; then
        if id "$user" > /dev/null 2>&1; then
            echo "User $user exists."
        else
            echo "Warning: User $user not found!"
        fi
    fi
done

echo "Assigning users to groups ..."
# Reset arrays for group assignment
declare -a assign_gnames assign_gids
while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*cn: ]]; then
        gname=$(echo "$line" | cut -d: -f2 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        assign_gnames+=("$gname")
    fi
done < "$GROUP_FILE"

while IFS= read -r line; do
    if [[ $line =~ ^[[:space:]]*gidNumber: ]]; then
        gid=$(echo "$line" | cut -d: -f2 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
        assign_gids+=("$gid")
    fi
done < "$GROUP_FILE"

for ((i=0; i<${#assign_gnames[@]}; i++)); do
    gid=${assign_gids[i]}
    if [ -n "$gid" ] && [ -n "${assign_gnames[i]}" ]; then
        echo "Group: ${assign_gnames[i]}"
        # Extract usernames for this group
        while IFS= read -r username; do
            if [ -n "$username" ]; then
                echo "$CLUSTER group add ${assign_gnames[i]} $username"
                $CLUSTER group add "${assign_gnames[i]}" "$username" || echo "Warning: Failed to add user $username to group ${assign_gnames[i]}"
            fi
        done < <(sed -n "/gidNumber: $gid/,/objectClass/p" "$GROUP_FILE" | sed -n 's/.*cn=\([^,]*\),.*/\1/p')
    fi
done

echo "LDAP data push completed successfully."
EOF
