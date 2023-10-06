#!/bin/bash

scripts=`realpath $0`
folder=`dirname $scripts`

source  "${folder}/rdma_metrics_collection_config.conf"
hours="$hoursAgoFromNow"
interval="$metricsCollectionIntervalInMinute"
par_filename="$parFileName"
cluster_name=""

if [ -z "$par_filename" ]
then
  echo "Please create a PAR and save into a file. Then, in config file, set the path of PAR-file  to parFileName"
  exit
fi

if [ ! -f ${par_filename} ]
then
   echo "PAR file:${par_filename} does not exist. Please create PAR file and update the config file"
   exit
fi

dis_help()
{
   echo
   echo "Usage:"
   echo
   echo "./upload_rdma_nic_metrics.sh -l <limit:hours ago from now> -i <Metrics Interval> -c <Cluster Name>"
   echo
   echo "Options:"
   echo "l     Hours Ago From Now (optional)"
   echo "i     Metrics Collection Interval In Minute (optional)"
   echo "c     Cluster Name (optional)"
   echo "h     Print this help."
   echo
   echo "RDMA metrics are uploaded to Object Storage using PAR"
   echo
   echo "e.g.,  sh ./upload_rdma_nic_metrics.sh -l 24 -i 5 -c clusterName1"
   echo
   echo "Supported releases: 2.10.3+"
   echo
}

#Do this if number of arguments passed is greater than 0
if [ "$#" -gt "0" ]
then
    while getopts "l:i:c:h" option
    do
        case $option in
            l) hours=${OPTARG};;
            i) interval=${OPTARG};;
            c) cluster_name=${OPTARG};;
            h) dis_help
               exit;;
           \?) # Invalid option
               echo "Error: Invalid option"
               exit;;
        esac
    done
fi

monitoring_folder=$folder/../monitoring

if [ -f $monitoring_folder/activated ]
then
  timestamp=$(date +%s)
  for i in {0..16}
  do
    measurementname="infiniband_mlx5_"$i"_hw_counters"
    measurementnameBackup="infiniband_mlx5_"$i"_hw_counters_backup"
    echo "Checking device mlx5_${i} for RDMA HW metrics...."
    query="SELECT MEAN(*) INTO ${measurementnameBackup} FROM ${measurementname} WHERE time < now() AND time > now() - ${hours}h GROUP BY time(${interval}m)"
    rows=$(influx -database 'telegraf' -execute "${query}" -format json | jq  '.results[0].series[0].values[0][1]')

    if [ "$rows" -eq 0 ]; then
       echo "Device mlx5_${i} does not have metrics to collect"
       echo "......................................................"
       continue
    fi

    filename="infiniband_mlx5_${i}_${timestamp}"
    filename_csv="${filename}.csv"
    filename_zip="${cluster_name}_${filename}.zip"

    echo "Collecting RDMA HW  metrics of device mlx5_${i}...."
    query="SELECT * FROM ${measurementnameBackup}"
    influx -database 'telegraf' -execute "${query}" -format csv > $filename_csv
    filename_csv_path="${folder}/${filename_csv}"
    if [ ! -f ${filename_csv_path} ]
    then
        echo "ERROR:${filename_csv_path} was not created."
        continue
    fi

    zip ${filename_zip} ${filename_csv}
    rm ${filename_csv}
    filename_zip_path="${folder}/${filename_zip}"
    if [ ! -f ${filename_zip_path} ]
    then
        echo "ERROR:${filename_zip_path} was not created."
        continue
    fi

    par=$(cat "${par_filename}")
    echo "Uploading RDMA HW Metrics to Object Stroage for device mlx5_${i}"
    curl  -X PUT --data-binary @${filename_zip} "$par""$filename_zip"
    echo "Uploaded RDMA HW metrics to Object Storage for device mlx5_${i}"
    echo "Object storage URL for device mlx_5${i}: ${par}${filename_zip}"

    sqldelete="DELETE FROM ${measurementnameBackup}"
    influx -database 'telegraf' -execute "${sqldelete}"
    echo "......................................................"
  done

  measurementname="infiniband"
  measurementnameBackup="infiniband_backup"

  echo "Checking for Infiniband counter metrics...."
  query="SELECT MEAN(*) INTO ${measurementnameBackup} FROM ${measurementname} WHERE time < now() AND time > now() - ${hours}h GROUP BY time(${interval}m)"
  rows=$(influx -database 'telegraf' -execute "${query}" -format json | jq  '.results[0].series[0].values[0][1]')

   if [ "$rows" -eq 0 ]; then
       echo "It does not have Infiniband counter metrics to collect"
   fi

  filename="infiniband_${timestamp}"
  filename_csv="${filename}.csv"
  filename_zip="${cluster_name}_${filename}.zip"

  echo "Collecting Infiniband counter  metrics...."
  query="SELECT * FROM ${measurementnameBackup}"
  influx -database 'telegraf' -execute "${query}" -format csv > $filename_csv
  filename_csv_path="${folder}/${filename_csv}"
  if [ ! -f ${filename_csv_path} ]
  then
    echo "ERROR:${filename_csv_path} was not created."
    continue
  fi

  zip ${filename_zip} ${filename_csv}
  rm ${filename_csv}
  filename_zip_path="${folder}/${filename_zip}"
  if [ ! -f ${filename_zip_path} ]
  then
    echo "ERROR:${filename_zip_path} was not created."
    continue
  fi

  echo "Uploading Infiniband counter metrics to Object Stroage"
  curl  -X PUT --data-binary @${filename_zip} "$par""$filename_zip"
  echo "Uploaded Infiniband counter  metrics to Object Storage"
  echo "Object storage URL for Infiniband counter metrics: ${par}${filename_zip}"

  sqldelete="DELETE FROM ${measurementnameBackup}"
  influx -database 'telegraf' -execute "${sqldelete}"

fi
