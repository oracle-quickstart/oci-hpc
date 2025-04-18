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
  /usr/bin/python3 $folder/resize/resize.py --help
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

  if [ -f $monitoring_folder/activated ]
  then
    source $monitoring_folder/env
    mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resize='$start_timestamp',state='resizing' WHERE id='$cluster_id'" >> $log 2>&1
  fi

  /usr/bin/python3 $folder/resize/resize.py ${@} | tee -a $log 2>&1 | grep STDOUT
  status=${PIPESTATUS[0]}
  end=`date -u +%s`
  end_timestamp=`date -u +'%F %T'`
  runtime=$((end-start))

  if [ $status -eq 0 ]
  then
    echo "Successfully Resized cluster $cluster_name in $runtime seconds"
    if [ -f $monitoring_folder/activated ]
    then
      nodes_list=`/usr/bin/python3 $folder/resize/resize.py --cluster_name $cluster_name list | grep ocid1.instance`

      length=`echo $nodes_list | wc -w`
      newSize=$((length/3))
      existing_nodes=`mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; select hostname from nodes WHERE cluster_id='$cluster_id' and state <> 'deleted';" 2>&1 | grep inst`
      max_index=`mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; select max(cluster_index) from nodes WHERE cluster_id='$cluster_id';" 2>&1 | tail -n 1`
      mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET nodes=$newSize,state='running',resize_log='$logs_folder/resize_${cluster_id}.log' WHERE id='$cluster_id'" >> $log 2>&1
      if [ $resize_type == "remove" ] || [ $resize_type == "remove_unreachable" ]
      then
        if [ "$nodes" == "NULL" ] || [ $resize_type == "remove_unreachable" ]
        then
          for node in $existing_nodes; do
            if [ `echo $nodes_list | grep $node | wc -l` == 0 ]
            then
              echo $node Deleted
              mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET started_deletion='$start_timestamp',deleted='$end_timestamp',state='deleted' WHERE cluster_id='$cluster_id' AND hostname='$node'" >> $log 2>&1
            fi
          done
        else
          for node in $nodes; do
            echo $node Deleted
            mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET started_deletion='$start_timestamp',deleted='$end_timestamp',state='deleted' WHERE cluster_id='$cluster_id' AND hostname='$node'" >> $log 2>&1
          done
        fi
      else
        for node in ${nodes_list}; do
            nl_array+=( $node )
        done
        length=`echo $nodes_list | wc -w`
        for (( c=0; c<=$((length-1)); c=c+3 )); do
          max_index=$((max_index+1))
          ip=`echo ${nl_array[$c+1]}`
          hostname=`echo ${nl_array[$((c))]}`
          ocid=`echo ${nl_array[$((c+2))]}`
          if [ `echo $existing_nodes | grep $hostname | wc -l` == 0 ]
          then
            max_index=$((max_index+1))
            mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; INSERT IGNORE INTO cluster_log.nodes (cluster_id,cluster_index,cpus,created,state,class_name,shape,hostname,ip,node_OCID) VALUES ('$cluster_name',$max_index,36,'$end_timestamp','running','$queue','$shape','${hostname}','${ip}','${ocid}');"  >> $log 2>&1
          fi
        done
      fi
    fi
  else
    echo "Could not resize cluster $cluster_name in 5 tries (Time: $runtime seconds)"
    if [ -f $monitoring_folder/activated ]
    then
      mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.errors_timeserie (cluster_id,state,error_log,error_type,created_on_m) VALUES ('$cluster_id','resize','$logs_folder/resize_${cluster_id}.log','`tail $log | grep Error`','$end_timestamp');" >> $log 2>&1
      mysql -u $ENV_MYSQL_USER -p$ENV_MYSQL_PASS -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resizing=NULL,state='running' WHERE id='$cluster_id'" >> $log 2>&1
    fi
  fi
  if [ $permanent -eq 0 ]
  then
    rm currently_resizing
  fi
else
  /usr/bin/python3 $folder/resize/resize.py ${@}
fi
