#!/bin/bash

if [ $# -eq 0 ]
then
  echo "No arguments supplied"
  exit
fi
date=`date -u '+%Y%m%d%H%M'`
start=`date -u +%s`
start_timestamp=`date -u +'%F %T'`
scripts=`realpath $0`
folder=`dirname $scripts`
cd $folder/clusters/$1
cluster_id=`cat cluster_id`
echo $date >> $folder/logs/delete_${cluster_id}.log 2>&1
if [ -f "currently_destroying" ] && [[ $2 != FORCE ]]
then 
    echo "The cluster is already being destroyed"
else
  echo $1 >> currently_destroying
  if [ -f $folder/../monitoring/activated ]
  then
    source $folder/../monitoring/env
    mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_deletion='$start_timestamp',state='deleting',deletion_tries=deletion_tries+1 WHERE id='$cluster_id'" >> $folder/logs/delete_${cluster_id}.log 2>&1
  fi
  if [ -f inventory ] 
  then
    echo `date -u '+%Y%m%d%H%M'` >> $folder/logs/delete_${cluster_id}.log 2>&1
    $folder/cleanup.sh $1 >> $folder/logs/delete_${cluster_id}.log 2>&1
    status_initial_deletion=$?
  else
    echo "The inventory file was never created, terraform failed before that step" >> $folder/logs/delete_${cluster_id}.log 2>&1
    status_initial_deletion=0
  fi
  if [ $status_initial_deletion -ne 0 ] && [[ $2 == FORCE ]]
  then
    echo `date -u '+%Y%m%d%H%M'` >> $folder/logs/delete_${cluster_id}.log 2>&1
    $folder/cleanup.sh $1 FORCE >> $folder/logs/delete_${cluster_id}.log 2>&1
    status_initial_deletion=$?
  fi
  i=0
  echo `date -u '+%Y%m%d%H%M'` >> $folder/logs/delete_${cluster_id}.log 2>&1
  terraform destroy -auto-approve -parallelism 5 >> $folder/logs/delete_${cluster_id}.log 2>&1
  status_terraform_deletion=$?
  while [ $i -lt 5 ] && [ $status_terraform_deletion -ne 0 ]
  do
    echo `date -u '+%Y%m%d%H%M'` >> $folder/logs/delete_${cluster_id}.log 2>&1
    terraform init >> $folder/logs/delete_${cluster_id}.log 2>&1
    terraform destroy -auto-approve >> $folder/logs/delete_${cluster_id}.log 2>&1
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
  if [ $status_initial_deletion -ne 0 ] 
  then
    echo "ANSIBLE initial cleanup has failed. This may have been resolved in the retry" >> $folder/logs/delete_${cluster_id}.log 2>&1
    if [ -f $folder/../monitoring/activated ]
    then
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.errors_timeserie (cluster_id,state,error_log,error_type,created_on_m) VALUES ('$cluster_id','deletion','$folder/logs/delete_${cluster_id}.log','Ansible Cleanup may not have finished properly `tail $folder/logs/delete_${cluster_id}.log | grep Error`','$end_timestamp');" >> $folder/logs/delete_${cluster_id}.log 2>&1
    fi
  fi
  if [ $status_terraform_deletion -eq 0 ]
  then
    echo "Successfully deleted cluster $1 in $runtime seconds"
    if [ -f $folder/../monitoring/activated ]
    then
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET deleted='$end_timestamp',state='deleted',deletion_time=SEC_TO_TIME($runtime),deletion_log='$folder/logs/delete_${cluster_id}.log',deletion_tries=deletion_tries+1 WHERE id='$cluster_id'" >> $folder/logs/delete_${cluster_id}.log 2>&1
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET started_deletion='$start_timestamp',deleted='$end_timestamp',state='deleted' WHERE cluster_id='$cluster_id'" >> $folder/logs/delete_${cluster_id}.log 2>&1
    fi
    cd
    rm -rf $folder/clusters/$1 | tee -a $folder/logs/delete_${cluster_id}.log 2>&1

  else
    echo "Could not delete cluster $1 in 5 tries (Time: $runtime seconds)"
    rm currently_destroying
    if [ -f $folder/../monitoring/activated ]
    then
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.errors_timeserie (cluster_id,state,error_log,error_type,created_on_m) VALUES ('$cluster_id','deletion','$folder/logs/delete_${cluster_id}.log','`tail $folder/logs/delete_${cluster_id}.log | grep Error`','$end_timestamp');" >> $folder/logs/delete_${cluster_id}.log 2>&1
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET started_deletion=NULL,state='running' WHERE id='$cluster_id'" >> $folder/logs/delete_${cluster_id}.log 2>&1
    fi
  fi
fi