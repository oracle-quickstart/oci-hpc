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
    apt -y --fix-broken install

    while true; do
        apt update
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

controller_name=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.controller_name`
cluster_name=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.cluster_name`
login=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.login`
monitoring=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.monitoring`
controller=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.controller`
hostname_convention=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .freeformTags.hostname_convention`

fss=fss-${controller_name}

fss_ip=$(host "${fss}" | awk '{print $4}')
controller_ip=$(host "${controller_name}"| awk '{print $4}')

if [ "$controller" == "true" ] && [ "$controller_name" == `hostname` ]; then
    echo "Do not run the cloud-init on the controller, this will create a circular dependency on the /config mount"
    exit
fi

mkdir /config

if [ "$fss_ip" == "$controller_ip" ]; then
    echo "FSS and controller are on the same host"
    if ! grep -qF "$controller_name:/config /config nfs" /etc/fstab; then
        echo "$controller_name:/config /config nfs defaults,noatime,bg,timeo=100,ac,actimeo=120,nocto,rsize=1048576,wsize=1048576,nolock,local_lock=all,mountproto=tcp,sec=sys,_netdev 0 0" >> /etc/fstab
        systemctl daemon-reload
        echo "Entry added to /etc/fstab."
    else
        echo "Entry already exists in /etc/fstab."
    fi
else
    if ! grep -qF "$fss:/config /config nfs" /etc/fstab; then
        echo "$fss:/config /config nfs defaults,nconnect=16 0 0" >> /etc/fstab
        systemctl daemon-reload
        echo "Entry added to /etc/fstab."
    else
        echo "Entry already exists in /etc/fstab."
    fi
fi

while true; do
    if mountpoint -q /config; then
        echo "/config is already mounted. Checking if files are present"
        ls /config/bin/compute.sh
        if [ $? -eq 0 ]; then 
            echo "/config/bin/compute.sh is present"
            break
        else
            echo "/config/bin/compute.sh is not present. Retrying in 2 minutes..."
            sleep 120  # Sleep for 2 minutes (120 seconds)
        fi     
    fi
    echo "Attempting to mount /config"
    # Run the mount command and check if it succeeds
    mount /config
    
    if [ $? -eq 0 ]; then
        ls /config/bin/compute.sh
        if [ $? -eq 0 ]; then
            echo "Mount succeeded!"
            break
        else
            echo "Mount failed. Retrying in 2 minutes..."
            sleep 120  # Sleep for 2 minutes (120 seconds)
        fi
    else
        echo "Mount failed. Retrying in 2 minutes..."
        sleep 120  # Sleep for 2 minutes (120 seconds)
    fi
done

if [ "$login" == "true" ]; then
    su - $default_user /config/bin/login.sh 2>&1 | tee -a /tmp/cloud-init.log
elif [ "$monitoring" == "true" ]; then
    su - $default_user /config/bin/monitoring.sh 2>&1 | tee -a /tmp/cloud-init.log
elif [ "$controller" != "true" ] ; then
    su - $default_user /config/bin/compute.sh $cluster_name 2>&1 | tee -a /tmp/cloud-init.log
fi