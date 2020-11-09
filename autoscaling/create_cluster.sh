#!/bin/bash

if [ $# -eq 0 ] || [ $# -eq 1 ]
then
  echo "No enough arguments supplied, please supply number of nodes and cluster name"
  exit
fi

scripts=`realpath $0`
folder=`dirname $scripts`
cp -r $folder/tf_init $folder/clusters/$2
cd $folder/clusters/$2
sed "s/##NODES##/$1/g;s/##NAME##/$2/g" $folder/tf_init/variables.tf > variables.tf
terraform init
echo $1 >> currently_building
terraform apply -auto-approve
if [ $? -eq 0 ]
  then
    echo "Successfully created cluster $2"
    rm currently_building
  else
    echo "Could not create cluster $1"
    rm currently_building
    terraform destroy -auto-approve
fi
