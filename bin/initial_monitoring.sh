#!/bin/bash

scripts=`realpath $0`
folder=`dirname $scripts`

end_timestamp=`date -u +'%F %T'`
bastionName=`hostname`
cluster_name=${bastionName/-bastion/}

autoscaling_folder=$folder/../autoscaling
monitoring_folder=$folder/../monitoring

if [ -f $monitoring_folder/activated ]
then
  ocid=`cat /tmp/initial.mon | grep "cluster_ocid =" | awk '{print $3}'`
  ips=`cat /tmp/initial.mon | grep "private_ips =" | awk '{print $3}'`
  ocids=`cat /tmp/initial.mon | grep "ocids =" | awk '{print $3}'`
  hostnames=`cat /tmp/initial.mon | grep "hostnames =" | awk '{print $3}'`
  queue=`cat /tmp/initial.mon | grep "queue =" | awk '{print $3}'`
  shape=`cat /tmp/initial.mon | grep "shape =" | awk '{print $3}'`
  cluster_network=`cat /tmp/initial.mon | grep "cluster_network =" | awk '{print $3}'`

  export IFS=","
  for ip in ${ips}; do
    ip_array+=( $ip )
  done
  for ocid in ${ocids}; do
    ocid_array+=( $ocid )
  done
  for hostname in ${hostnames}; do
    hostname_array+=( $hostname )
  done
  source $monitoring_folder/env
  mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.clusters (id,nodes,class_name,shape,CN,cpu_per_node,cluster_name,state,created,cluster_OCID) VALUES ('$cluster_name','${#ip_array[@]}','$queue','$shape',$cluster_network,36,'$cluster_name','running','$end_timestamp','$ocid');"
  for index in "${!ip_array[@]}"; do
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.nodes (cluster_id,cluster_index,cpus,created,state,class_name,shape,hostname,ip,node_OCID) VALUES ('$cluster_name',$index,36,'$end_timestamp','running','$queue','$shape','${hostname_array[$index]}','${ip_array[$index]}','${ocid_array[$index]}');" 
  done
fi