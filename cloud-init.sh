#!/bin/bash
source /etc/os-release
if [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then 
    default_user=ubuntu
    function fix_apt {
        apt_process=`ps aux | grep "apt update" | grep -v grep | wc -l`
        apt_process=$(( apt_process -1 ))
        while [ $apt_process -ge 1 ]
        do
            echo "wait until apt update is done"
            sleep 10s
            ps aux | grep "apt update" | grep -v grep
            apt_process=`ps aux | grep "apt update" | grep -v grep | wc -l`
            apt_process=$(( apt_process -1 ))
        done
    }
    fix_apt

    sleep 10s
    sudo apt -y --fix-broken install

    while true; do
        apt install -y jq
        if [ $? -eq 0 ]; then
            echo "jq installed"
            break
        else
            echo "jq install failed. Retrying in 10s..."
            sleep 10  # Sleep for 10 seconds
        fi
    done
else
    default_user=opc
fi

controller=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.controller_name`
cluster_name=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.cluster_name`

mkdir /config

echo "$controller:/config /config nfs defaults,noatime,bg,timeo=100,ac,actimeo=120,nocto,rsize=1048576,wsize=1048576,nolock,local_lock=all,mountproto=tcp,sec=sys,_netdev 0 0" >> /etc/fstab
systemctl daemon-reload

while true; do
    if mountpoint -q /config; then
        echo "/config is already mounted. Exiting loop."
        break
    fi
    echo "Attempting to mount $controller:/config"
    # Run the mount command and check if it succeeds
    mount /config
    
    if [ $? -eq 0 ]; then
        echo "Mount succeeded!"
        break
    else
        echo "Mount failed. Retrying in 2 minutes..."
        sleep 120  # Sleep for 2 minutes (120 seconds)
    fi
done

su - $default_user /config/compute.sh $cluster_name 2>&1 | tee -a /tmp/cloud-init.log