#!/bin/bash
echo test

controller=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.controller_name`
cluster_name=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.cluster_name`

mkdir /config

while true; do
    echo "Attempting to mount $controller:/config"
    # Run the mount command and check if it succeeds
    mount $controller:/config /config
    
    if [ $? -eq 0 ]; then
        echo "Mount succeeded!"
        break
    else
        echo "Mount failed. Retrying in 2 minutes..."
        sleep 120  # Sleep for 2 minutes (120 seconds)
    fi
done

/config/compute.sh $cluster_name 2>&1 | tee -a /tmp/cloud-init.log