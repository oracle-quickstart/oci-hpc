#!/bin/bash

date=`date -u '+%Y%m%d%H%M'`
start=`date -u +%s`
start_timestamp=`date -u +'%F %T'`
scripts=`realpath $0`
folder=`dirname $scripts`
autoscaling_folder=$folder/../autoscaling
monitoring_folder=$folder/../monitoring
logs_folder=$folder/../logs

if [ $EUID -eq 0 ]
then
  echo "Run this script as opc or ubuntu and not as root"
  exit
fi

if [ $USER != "ubuntu" ] && [ $USER != "opc" ]
then
  echo "Run this script as opc or ubuntu"
  exit
fi

if [ $# -eq 0 ] || [ $1 == "--help" ]
then
  source /config/venv/bin/activate
  /config/venv/bin/python3 $folder/resize.py --help
  exit
fi

resize_type=default
permanent=1
controllerName=`hostname`
cluster_name=${controllerName/-controller/}
nodes=NULL
quietMode=False
for (( i=1; i<=$#; i++)); do
    if [ ${!i} == "--cluster_name" ]
    then
        j=$((i+1))
        if [ $cluster_name != ${!j} ]
        then
          permanent=0
        fi
        cluster_name=${!j}
    elif [ ${!i} == "add" ]
    then
      resize_type=add
    elif [ ${!i} == "remove" ]
    then
      resize_type=remove
    elif [ ${!i} == "remove_unreachable" ]
    then
      resize_type=remove_unreachable
    elif [ ${!i} == "--nodes" ]
    then
      j=$((i+1))
      nodes=${@:j}
    elif [ ${!i} == "--quiet" ]
    then
      quietMode=True
    fi
done

if [ $resize_type == "remove" ] || [ $resize_type == "remove_unreachable" ] && [ $quietMode == "False" ]
then
  echo "$(cat $folder/remove_nodes_prompt.txt)"
  echo "Do you confirm you have done all of the above steps and wish to proceed for the termination of the nodes? Enter 1 for Yes and 2 for No (to exit)."
  select yn in "Yes" "No"; do
    case $yn in
        Yes ) break;;
        No ) exit;;
    esac
  done
fi

if [ $resize_type != "default" ]
then
  if [ $permanent -eq 0 ]
  then
    cd $autoscaling_folder/clusters/$cluster_name
    cluster_id=`cat cluster_id`
    shape=`cat inventory | grep shape= | awk -F  "=" '{print $2}'`
    queue=`cat inventory | grep queue= | awk -F  "=" '{print $2}'`
    log=$logs_folder/resize_${cluster_id}.log
    echo $date >> ${log} 2>&1
    if [ -f "currently_resizing" ] && [[ $2 != FORCE ]]
    then
      echo "The cluster is already being resized"
      exit
    else
      echo $cluster_name >> currently_resizing
      echo `date -u '+%Y%m%d%H%M'` >> $log 2>&1
    fi
  else
    cluster_id=$cluster_name
    shape=`cat /etc/ansible/hosts | grep shape= | awk -F  "=" '{print $2}'`
    queue=`cat /etc/ansible/hosts | grep queue= | awk -F  "=" '{print $2}'`
    log=$logs_folder/resize_${cluster_id}.log
  fi

  source /config/venv/bin/activate
  /config/venv/bin/python3 $folder/resize.py ${@} | tee -a $log 2>&1 | grep STDOUT
  status=${PIPESTATUS[0]}
  end=`date -u +%s`
  end_timestamp=`date -u +'%F %T'`
  runtime=$((end-start))

  if [ $status -eq 0 ]
  then
    echo "Successfully Resized cluster $cluster_name in $runtime seconds"
  else
    echo "Could not resize cluster $cluster_name in 5 tries (Time: $runtime seconds)"
  fi
  if [ $permanent -eq 0 ]
  then
    rm currently_resizing
  fi
else
  source /config/venv/bin/activate
  /config/venv/bin/python3 $folder/resize.py ${@}
fi
