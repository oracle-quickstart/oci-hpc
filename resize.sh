#!/bin/bash

date=`date -u '+%Y%m%d%H%M'`
start=`date -u +%s`
start_timestamp=`date -u +'%F %T'`
scripts=`realpath $0`
folder=`dirname $scripts`

if [ $# -eq 0 ]
then
  python3 $folder/resize.py --help
  exit
fi

resize_type=default
permanent=1
bastionName=`hostname`
cluster_name=${bastionName/-bastion/}
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
    fi
done

if [ $resize_type != "default" ]
then
  if [ $permanent -eq 0 ]
  then
    cd $folder/../autoscaling/clusters/$cluster_name
    cluster_id=`cat cluster_id`
    shape=`cat inventory | grep shape= | awk -F  "=" '/1/ {print $2}'`
    queue=`cat inventory | grep queue= | awk -F  "=" '/1/ {print $2}'`
    log=$folder/../autoscaling/logs/resize_${cluster_id}.log
    echo $date >> ${log} 2>&1
    if [ -f "currently_resizing" ] && [[ $2 != FORCE ]]
    then
      echo "The cluster is already being resized"
    else
      echo $1 >> currently_resizing
      echo `date -u '+%Y%m%d%H%M'` >> $log 2>&1
    fi
  else
    cluster_id=$cluster_name
    shape=`cat /etc/ansible/hosts | grep shape= | awk -F  "=" '/1/ {print $2}'`
    queue=`cat /etc/ansible/hosts | grep queue= | awk -F  "=" '/1/ {print $2}'`
    log=$folder/../autoscaling/logs/resize_${cluster_id}.log
  fi


  if [ -f $folder/../monitoring/activated ]
  then
    source $folder/../monitoring/env
    mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resize='$start_timestamp',state='resizing' WHERE id='$cluster_id'" >> $log 2>&1
  fi

  python3 $folder/../bin/resize.py ${@} >> $log 2>&1
  status=$?
  end=`date -u +%s`
  end_timestamp=`date -u +'%F %T'`
  runtime=$((end-start))

  if [ $status -eq 0 ]
  then
    echo "Successfully Resized cluster $1 in $runtime seconds"
    if [ -f $folder/../monitoring/activated ]
    then
      newSize=`python3 $folder/../bin/resize.py --cluster_name $cluster_name list | grep inst- | wc -l`
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET nodes=$newSize,state='running',resize_log='$folder/logs/resize_${cluster_id}.log' WHERE id='$cluster_id'" >> $log 2>&1
      if [ $resize_type == "remove" ]
      then
        for node in ${@:2}; do
          echo $node Deleted
          mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET started_deletion='$start_timestamp',deleted='$end_timestamp',state='deleted' WHERE cluster_id='$cluster_id' AND hostname='$node'" >> $log 2>&1
        done
      else
        nodes_list=`python3 $folder/../bin/resize.py --cluster_name $cluster_name list | grep ocid1.instance`
        for node in ${nodes_list}; do
          nl_array+=( $node )
        done
        length=`echo $nodes_list | wc -w`
        for (( c=1; c<=$length; c=c+3 )); do
          ip=`echo ${nl_array[$c]}`
          hostname=`echo ${nl_array[$((c+2))]}`
          ocid=`echo ${nl_array[$((c+1))]}`
          mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT IGNORE INTO cluster_log.nodes (cluster_id,cpus,created,state,class_name,shape,hostname,ip,node_OCID) VALUES ('$cluster_name',36,'$end_timestamp','running','$queue','$shape','${hostname}','${ip}','${ocid}');"  >> $log 2>&1
        done
      fi
    fi
  else
    echo "Could not resize cluster $1 in 5 tries (Time: $runtime seconds)"
    if [ -f $folder/../monitoring/activated ]
    then
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.errors_timeserie (cluster_id,state,error_log,error_type,created_on_m) VALUES ('$cluster_id','resize','$folder/logs/resize_${cluster_id}.log','`tail $log | grep Error`','$end_timestamp');" >> $log 2>&1
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resizing=NULL,state='running' WHERE id='$cluster_id'" >> $log 2>&1
    fi
    rm currently_resizing
  fi
else
  python3 $folder/../bin/resize.py ${@}
fi