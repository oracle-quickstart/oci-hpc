#!/bin/bash

if [ $# -eq 0 ]
then
  echo "No arguments supplied, Expecting clustername and space separated list of nodes"
  exit
fi
date=`date -u '+%Y%m%d%H%M'`
start=`date -u +%s`
start_timestamp=`date -u +'%F %T'`
scripts=`realpath $0`
folder=`dirname $scripts`
cd $folder/clusters/$1
cluster_id=`cat cluster_id`
echo $date >> $folder/logs/resize_${cluster_id}.log 2>&1
if [ -f "currently_resizing" ] && [[ $2 != FORCE ]]
then 
    echo "The cluster is already being resized"
else
  echo $1 >> currently_resizing
  if [ -f $folder/../monitoring/activated ]
  then
    source $folder/../monitoring/env
    mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resize='$start_timestamp',state='resizing' WHERE id='$cluster_id'" >> $folder/logs/resize_${cluster_id}.log 2>&1
  fi
  i=0
  echo `date -u '+%Y%m%d%H%M'` >> $folder/logs/resize_${cluster_id}.log 2>&1
  python3 $folder/../bin/resize.py --cluster_name $1 remove --nodes ${@:2} >> $folder/logs/resize_${cluster_id}.log 2>&1
  status_terraform_deletion=$?
  while [ $i -lt 2 ] && [ $status_terraform_deletion -ne 0 ]
  do
    echo `date -u '+%Y%m%d%H%M'` >> $folder/logs/resize_${cluster_id}.log 2>&1
    python3 $folder/../bin/resize.py --cluster_name $1 remove --nodes ${@:2} >> $folder/logs/resize_${cluster_id}.log 2>&1
    status_terraform_deletion=$?
    ((i++))
    if [ $status_terraform_deletion -eq 0 ]; then
      break
    fi
    sleep 120
  done 
  end=`date -u +%s`
  end_timestamp=`date -u +'%F %T'`
  runtime=$((end-start))
  if [ $status_terraform_deletion -eq 0 ]
  then
    echo "Successfully Resized cluster $1 in $runtime seconds"
    if [ -f $folder/../monitoring/activated ]
    then
      newSize=`python3 $folder/../bin/resize.py --cluster_name $1 list | grep inst- | wc -l`
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET nodes=$newSize,state='running',resize_log='$folder/logs/resize_${cluster_id}.log' WHERE id='$cluster_id'" >> $folder/logs/delete_${cluster_id}.log 2>&1
      for node in ${@:2}; do
        echo $node Deleted
        mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET started_deletion='$start_timestamp',deleted='$end_timestamp',state='deleted' WHERE cluster_id='$cluster_id' AND hostname='$node'" >> $folder/logs/resize_${cluster_id}.log 2>&1
      done
    fi

  else
    echo "Could not resize cluster $1 in 5 tries (Time: $runtime seconds)"
    if [ -f $folder/../monitoring/activated ]
    then
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.errors_timeserie (cluster_id,state,error_log,error_type,created_on_m) VALUES ('$cluster_id','resize','$folder/logs/resize_${cluster_id}.log','`tail $folder/logs/resize_${cluster_id}.log | grep Error`','$end_timestamp');" >> $folder/logs/resize_${cluster_id}.log 2>&1
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_resizing=NULL,state='running' WHERE id='$cluster_id'" >> $folder/logs/resize_${cluster_id}.log 2>&1
    fi
  fi
  rm currently_resizing
fi