#!/bin/bash
exec >> /var/log/slurm/resume.log 2>&1
# Expand the hostlist from the first argument
hosts=$(scontrol show hostnames "$1")

declare -A cluster_hosts
declare -A cluster_types

source /etc/os-release

# Group hosts by their partition (cluster name)
for host in $hosts; do
    partition=$(sinfo -N -n "$host" -o "%P" -h | awk '{print $1}')
    instance_type=$(sinfo -N -n "$host" -o "%f" -h | awk '{print $1}')

    # Append host with a comma separator
    cluster_hosts["$partition"]+="$host,"
    cluster_types["$partition"]="$instance_type"
done

# Iterate over each partition and run either create or add
for cluster in "${!cluster_hosts[@]}"; do
    # Clean trailing comma
    host_list=${cluster_hosts[$cluster]%,}
    instance_type=${cluster_types[$cluster]}
    count=$(echo "$host_list" | tr ',' '\n' | wc -l)
    echo $(date)
    echo $host_list $instance_type $count
    if /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci/bin/python3 /config/mgmt/manage.py clusters list --format json | jq -e ".[] | select(. == \"$cluster\")" > /dev/null; then
        echo "Adding nodes to existing cluster: $cluster"
        /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci/bin/python3 /config/mgmt/manage.py clusters add node --cluster "$cluster" --count "$count" --names "$host_list"
    else
        echo "Creating new cluster: $cluster"
        /config/venv/${ID^}_${VERSION_ID}_$(uname -m)/oci/bin/python3 /config/mgmt/manage.py clusters create --cluster "$cluster" --count "$count" --instancetype "$instance_type" --names "$host_list"
    fi
done