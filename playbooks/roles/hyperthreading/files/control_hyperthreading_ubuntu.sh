#!/bin/bash
if [ `id -u` -ne 0 ]
then
        echo $0: you need to be root
        exit 1
fi
disable_ht() {
        echo -n $0: disabling
        echo off | sudo tee /sys/devices/system/cpu/smt/control
}

enable_ht() {
        echo -n $0: enabling
        echo on | sudo tee /sys/devices/system/cpu/smt/control
}

case "$1" in
"1"|"on")
        enable_ht
        ;;
"0"|"off")
        disable_ht
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