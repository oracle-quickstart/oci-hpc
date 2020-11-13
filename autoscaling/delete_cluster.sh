#!/bin/bash

if [ $# -eq 0 ]
then
  echo "No arguments supplied"
  exit
fi
date=`date '+%Y%m%d%H%M'`
start=`date +%s`
scripts=`realpath $0`
folder=`dirname $scripts`
cd $folder/clusters/$1
if [ -f "currently_destroying" ]
then 
    echo "The cluster is already being destroyed"
else
  echo $1 >> currently_destroying
  terraform destroy -auto-approve >> $folder/logs/delete_$1_${date}.log
status=$?
end=`date +%s`
runtime=$((end-start))
  if [ $status -eq 0 ]
  then
    echo "Successfully deleted cluster $1 in $runtime seconds"
    cd
    rm -rf $folder/clusters/$1
  else
    echo "Could not delete cluster $1 (Time: $runtime seconds)"
    rm currently_destroying
  fi
fi