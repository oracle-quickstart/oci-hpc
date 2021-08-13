#!/bin/bash

set -o pipefail

PATH="/usr/local/bin:/bin:/usr/bin:/sbin:/usr/local/sbin:/usr/sbin:/opt/ibutils/bin:"

if [ $# -ne 1 ]
then
        echo $0: usage: $0 'on|1' to enable hyper-threading.
        echo $0: usage: $0 'off|0' to disable hyper-threading.
        echo $0: usage: $0 'show' to show hyper-threading.
        exit 1
fi

if [ `id -u` -ne 0 ]
then
        echo $0: you need to be root
        exit 1
fi

disable_ht() {
	echo -n $0: disabling 
        for f in `cat /sys/devices/system/cpu/cpu*/topology/thread_siblings_list | sort --unique --numeric-sort`
        do
                __th2=`echo $f | awk -F , '{ print $2; }'`
                if [ "$__th2" != "" ]
                then
                        echo -n ' ' cpu"$__th2"
                        echo 0 > "/sys/devices/system/cpu/cpu"$__th2"/online"
                fi
        done
	echo
}

enable_ht() {
	echo -n $0: enabling 
        for f in `echo /sys/devices/system/cpu/cpu[0-9]*`
        do
                __enabled=`cat $f"/online"`
                if [ $__enabled -eq 0 ]
                then
                        echo -n ' ' `basename $f`
                        echo 1 > $f"/online"
                fi
        done
	echo ''
}

#
# rebalance_irqs() {
# 	echo -n rebalancing IRQs
# 	systemctl restart irqbalance
# 	echo -n '.'; sleep 1
# 	echo -n '.'; sleep 1
# 	echo -n '.'; sleep 1
# 	echo ''
# }
#

case "$1" in
"1"|"on")
        enable_ht
        #rebalance_irqs
        ;;
"0"|"off")
        disable_ht
        #rebalance_irqs
        ;;
"show")
	;;
*)
        echo $0: wrong argument "$1"
        exit 2
        ;;
esac

echo ''
lscpu | egrep "On-line|Off-line"

exit 0

