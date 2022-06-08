#!/bin/bash

date=`date -u '+%Y%m%d%H%M'`
start=`date -u +%s`
start_timestamp=`date -u +'%F %T'`
scripts=`realpath $0`
folder=`dirname $scripts`
autoscaling_folder=$folder/../autoscaling
monitoring_folder=$folder/../monitoring
logs_folder=$folder/../logs

if [ $# -eq 0 ]
then
  python3 $folder/resize.py --help
  exit
fi

resize_type=default
permanent=1
bastionName=`hostname`
cluster_name=${bastionName/-bastion/}
nodes=NULL
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
    elif [ ${!i} == "--nodes" ]
    then
      j=$((i+1))
      nodes=${@:j}
    fi
done

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
    mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resize='$start_timestamp',state='resizing' WHERE id='$cluster_id'" >> $log 2>&1
  fi

  python3 $folder/resize.py ${@} >> $log 2>&1
  status=$?
  end=`date -u +%s`
  end_timestamp=`date -u +'%F %T'`
  runtime=$((end-start))

  if [ $status -eq 0 ]
  then
    echo "Successfully Resized cluster $cluster_name in $runtime seconds"
    if [ -f $monitoring_folder/activated ]
    then
      nodes_list=`python3 $folder/resize.py --cluster_name $cluster_name list | grep ocid1.instance`

      length=`echo $nodes_list | wc -w`
      newSize=$((length/3))
      existing_nodes=`mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; select hostname from nodes WHERE cluster_id='$cluster_id' and state <> 'deleted';" 2>&1 | grep inst`
      max_index=`mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; select max(cluster_index) from nodes WHERE cluster_id='$cluster_id';" 2>&1 | tail -n 1`
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET nodes=$newSize,state='running',resize_log='$logs_folder/resize_${cluster_id}.log' WHERE id='$cluster_id'" >> $log 2>&1
      if [ $resize_type == "remove" ]
      then
        if [ "$nodes" == "NULL" ]
        then
          for node in $existing_nodes; do
            if [ `echo $nodes_list | grep $node | wc -l` == 0 ]
            then
              echo $node Deleted
              mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET started_deletion='$start_timestamp',deleted='$end_timestamp',state='deleted' WHERE cluster_id='$cluster_id' AND hostname='$node'" >> $log 2>&1
            fi
          done
        else
          for node in $nodes; do
            echo $node Deleted
            mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET started_deletion='$start_timestamp',deleted='$end_timestamp',state='deleted' WHERE cluster_id='$cluster_id' AND hostname='$node'" >> $log 2>&1
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
            mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT IGNORE INTO cluster_log.nodes (cluster_id,cluster_index,cpus,created,state,class_name,shape,hostname,ip,node_OCID) VALUES ('$cluster_name',$max_index,36,'$end_timestamp','running','$queue','$shape','${hostname}','${ip}','${ocid}');"  >> $log 2>&1
          fi
        done
      fi
    fi
  else
    echo "Could not resize cluster $cluster_name in 5 tries (Time: $runtime seconds)"
    if [ -f $monitoring_folder/activated ]
    then
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.errors_timeserie (cluster_id,state,error_log,error_type,created_on_m) VALUES ('$cluster_id','resize','$logs_folder/resize_${cluster_id}.log','`tail $log | grep Error`','$end_timestamp');" >> $log 2>&1
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resizing=NULL,state='running' WHERE id='$cluster_id'" >> $log 2>&1
    fi
  fi
  if [ $permanent -eq 0 ]
  then
    rm currently_resizing
  fi
else
  python3 $folder/resize.py ${@}
fi
