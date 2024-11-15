#!/bin/bash
echo test

source /etc/os-release
if [ $ID == "debian" ] || [ $ID == "ubuntu" ] ; then 
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
    sudo sed -i 's/"1"/"0"/g' /etc/apt/apt.conf.d/20auto-upgrades
    sudo apt purge -y --auto-remove unattended-upgrades
    sudo systemctl disable apt-daily-upgrade.timer
    sudo systemctl mask apt-daily-upgrade.service
    sudo systemctl disable apt-daily.timer
    sudo systemctl mask apt-daily.service
    
    sleep 10s

    sudo apt-mark hold linux-oracle linux-headers-oracle linux-image-oracle

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
fi

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