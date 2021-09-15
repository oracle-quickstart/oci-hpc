#!/bin/bash
if [ $# -eq 0 ] || [ $# -eq 1 ]
then
  echo "No enough arguments supplied, please supply number of nodes, cluster name, instance type, queue name, trigger Job ID and comma separated list of tags"
  exit
fi
date=`date '+%Y%m%d%H%M'`
scripts=`realpath $0`
folder=`dirname $scripts`

cp -r $folder/tf_init $folder/clusters/$2
cd $folder/clusters/$2
echo $1 $3 $4 >> currently_building
shape=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.shape " $folder/queues.conf`
cluster_network=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.cluster_network " $folder/queues.conf`
targetCompartment=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.targetCompartment " $folder/queues.conf`
ad=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.ad " $folder/queues.conf`
boot_volume_size=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.boot_volume_size " $folder/queues.conf`
use_marketplace_image=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.use_marketplace_image " $folder/queues.conf`
image=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.image " $folder/queues.conf`
instance_pool_ocpus=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.instance_pool_ocpus " $folder/queues.conf`
instance_pool_memory=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.instance_pool_memory " $folder/queues.conf`
instance_pool_custom_memory=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.instance_pool_custom_memory " $folder/queues.conf`
marketplace_listing=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.marketplace_listing " $folder/queues.conf`
hyperthreading=`yq eval ".queues.[] | select(.name == \"$4\") | .instance_types.[] | select(.name == \"$3\") |.hyperthreading " $folder/queues.conf`

sed "s/##NODES##/$1/g;s/##NAME##/$2/g;s/##SHAPE##/$shape/g;s/##CN##/$cluster_network/g;s/##QUEUE##/${4}/g;s/##COMP##/${targetCompartment}/g;s/##AD##/${ad}/g;s/##BOOT##/${boot_volume_size}/g;s/##USEMP##/${use_marketplace_image}/g;s/##IMAGE##/${image}/g;s/##OCPU##/${instance_pool_ocpus}/g;s/##MEM##/${instance_pool_memory}/g;s/##CUSTOM_MEM##/${instance_pool_custom_memory}/g;s/##MP_LIST##/${marketplace_listing}/g;s/##HT##/${hyperthreading}/g;s/##INST_TYPE##/$3/g;s/##TAGS##/$6/g" $folder/tf_init/variables.tf > variables.tf

echo "Started to build $2"
start=`date -u +%s`
start_timestamp=`date -u +'%F %T'`
echo $2_${date} > cluster_id
if [ -f $folder/../monitoring/activated ]
then
  source $folder/../monitoring/env
  mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.clusters (id,creation_log,nodes,trigger_job_id,class_name,shape,CN,cpu_per_node,cluster_name,state,started_creation) VALUES ('$2_${date}','create_$2_${date}.log','$1','$5','$4','$shape',$cluster_network,36,'$2','creating','$start_timestamp');" >> $folder/logs/create_$2_${date}.log 2>&1
  for i in $(eval echo "{1..$1}"); do
    mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.nodes (cluster_id,cluster_index,cpus,started_creation,state,class_name,shape) VALUES ('$2_${date}',$i,36,'$start_timestamp','provisioning','$4','$shape');" >> $folder/logs/create_$2_${date}.log 2>&1
  done
fi

echo `date -u '+%Y%m%d%H%M'` >> $folder/logs/create_$2_${date}.log 2>&1
terraform init >> $folder/logs/create_$2_${date}.log 2>&1
echo $1 $3 $4 >> currently_building
terraform apply -auto-approve -parallelism $1 >> $folder/logs/create_$2_${date}.log 2>&1
status=$?
end=`date -u +%s`
end_timestamp=`date -u +'%F %T'`
runtime=$((end-start))
if [ $status -eq 0 ]
  then
    echo "Successfully created $2 in $runtime seconds"
    rm currently_building
    if [ -f $folder/../monitoring/activated ]
    then
      ocid=`tail $folder/logs/create_$2_${date}.log | grep "cluster_ocid =" | awk '{print $3}'`
      ips=`tail $folder/logs/create_$2_${date}.log | grep "private_ips =" | awk '{print $3}'`
      hostnames=`tail $folder/logs/create_$2_${date}.log | grep "hostnames =" | awk '{print $3}'`
      ocids=`tail $folder/logs/create_$2_${date}.log | grep "ocids =" | awk '{print $3}'`
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET cluster_OCID='${ocid:1:-1}',created='$end_timestamp',state='running',creation_time=SEC_TO_TIME($runtime) WHERE id='$2_${date}';" >> $folder/logs/create_$2_${date}.log 2>&1
      export IFS=","
      for ip in ${ips:1:-5}; do
        ip_array+=( $ip )
      done
      for ocid in ${ocids:1:-5}; do
        ocid_array+=( $ocid )
      done
      for hostname in ${hostnames:1:-1}; do
        hostname_array+=( $hostname )
      done
      for index in "${!ip_array[@]}"; do
          mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.nodes SET created='$end_timestamp',state='running',hostname='${hostname_array[$index]}',ip='${ip_array[$index]}',node_OCID='${ocid_array[$index]}' WHERE cluster_id='$2_${date}' AND cluster_index=$(($index+1));" >> $folder/logs/create_$2_${date}.log 2>&1
      done
    fi
  else
    ERROR_MSG=`cat $folder/logs/create_$2_${date}.log | grep Error: | grep -o 'Output.*'`
    if [ "$ERROR_MSG" == "" ]
    then
        ERROR_MSG=`cat $folder/logs/create_$2_${date}.log | grep Error:`
    fi
    comp_tmp=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .compartmentId`
    compartment_ocid=${comp_tmp:1:-1}

    region_tmp=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .region`
    region=${region_tmp:1:-1}
    inst_pool_ocid=`oci compute-management instance-pool list --compartment-id $compartment_ocid  --auth instance_principal --region $region --all --display-name $2 | jq '.data | sort_by(."time-created" | split(".") | .[0] | strptime("%Y-%m-%dT%H:%M:%S")) |.[-1] .id'` >> $folder/logs/create_$2_${date}.log 2>&1
    requestID=`oci work-requests work-request list --compartment-id $compartment_ocid  --auth instance_principal --region $region --all --resource-id ${inst_pool_ocid:1:-1} | jq '.data | .[] | select(."operation-type"=="LaunchInstancesInPool") | .id'` >> $folder/logs/create_$2_${date}.log 2>&1
    inst_pool_work_request_error_messages=`oci work-requests work-request-error list --work-request-id ${requestID:1:-1} --auth instance_principal --region $region --all | jq '.data | .[] | .message '` >> $folder/logs/create_$2_${date}.log 2>&1
    if [ "$inst_pool_work_request_error_messages" == "" ]
    then
        cn_ocid=`oci compute-management cluster-network list --compartment-id $compartment_ocid  --auth instance_principal --region $region --all --display-name $2 | jq '.data | sort_by(."time-created" | split(".") | .[0] | strptime("%Y-%m-%dT%H:%M:%S")) |.[-1] .id'` >> $folder/logs/create_$2_${date}.log 2>&1
        requestID=`oci work-requests work-request list --compartment-id $compartment_ocid  --auth instance_principal --region $region --all --resource-id ${cn_ocid:1:-1} | jq '.data | .[] | select(."operation-type"=="CreateClusterNetworkReservation") | .id'` >> $folder/logs/create_$2_${date}.log 2>&1
        cn_work_request_error_messages=`oci work-requests work-request-log-entry list --work-request-id ${requestID:1:-1} --auth instance_principal --region $region --all | jq '.data | .[] | .message '` >> $folder/logs/create_$2_${date}.log 2>&1
    fi
    echo "$ERROR_MSG $inst_pool_work_request_error_messages $cn_work_request_error_messages" >> $folder/logs/create_$2_${date}.log 2>&1
    echo "Could not create $2 with $1 nodes in $runtime seconds"
    
    if [ -f $folder/../monitoring/activated ]
    then
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; INSERT INTO cluster_log.errors_timeserie (cluster_id,state,error_log,error_type,nodes,created_on_m) VALUES ('$2_${date}','creation','$folder/logs/create_$2_${date}.log','$ERROR_MSG $inst_pool_work_request_error_messages $cn_work_request_error_messages','$1','$end_timestamp');" >> $folder/logs/create_$2_${date}.log 2>&1
      mysqlsh $ENV_MYSQL_USER@$ENV_MYSQL_HOST -p$ENV_MYSQL_PASS --sql -e "use $ENV_MYSQL_DATABASE_NAME; UPDATE cluster_log.clusters SET state='deleting',creation_error='`tail $folder/logs/create_$2_${date}.log | grep Error`' WHERE id='$2_${date}';" >> $folder/logs/create_$2_${date}.log 2>&1
    fi
    rm currently_building
    $folder/delete_cluster.sh $2 FORCE
fi
