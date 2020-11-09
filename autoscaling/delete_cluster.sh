#!/bin/bash

if [ $# -eq 0 ]
then
  echo "No arguments supplied"
  exit
fi


scripts=`realpath $0`
folder=`dirname $scripts`
cd $folder/clusters/$1
if [ -f "currently_destroying" ]
then 
    echo "The cluster is already being destroyed"
else
  echo $1 >> currently_destroying
  terraform destroy -auto-approve
  if [ $? -eq 0 ]
  then
    echo "Successfully deleted cluster $1"
    cd
    rm -rf $folder/clusters/$1
  else
    echo "Could not delete cluster $1"
    rm currently_destroying
  fi
fi