#!/bin/bash

# run ib_write_bw between two nodes
# If on bastion: ./ib_write_bw.sh <server> <client>
# If on one compute node:  ./ib_write_bw.sh <server>

Server=$1
Client=${2:-localhost}
Dev=${3:-mlx5_17}
shape=`ssh $Server 'curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape'`
if [ "$shape" == "BM.GPU4.8" ]; then
   HCA="mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_13 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.GPU.A100-v2.8" ]; then
   HCA="mlx5_1 mlx5_2 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.GPU.H100.8" ]; then
   HCA="mlx5_0 mlx5_1 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_12 mlx5_13 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.GPU.H200.8" ]; then
   HCA="mlx5_0 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_9 mlx5_10 mlx5_11"
elif [ "$shape" == "BM.GPU.B4.8" ]; then
   HCA="mlx5_1 mlx5_2 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.Optimized3.36" ]; then
   HCA="mlx5_2"
else
   echo "Shape $shape not supported"
fi
cmd_base="/usr/bin/ib_write_bw -a -F -q 2 --report_gbits"
cmd_base="/usr/bin/ib_write_bw -b -F -q 2 -x 3 --report_gbits"
cmd_base="/usr/bin/ib_write_bw -b -F -q 2 -x 3 --report_gbits"
for Dev in $HCA; do
   echo -e "$Server $Client $Dev \c"
   ssh $Server exec $cmd_base -d $Dev > /dev/null 2>&1 &
   # make sure the server start listening before client make requests
   sleep 1
   BW=`ssh $Client $cmd_base -d $Dev $Server | grep "65536      10000" | awk '{print $3}'`
   #BW=`ssh $Client $cmd_base -d $Dev $Server `
   echo "$BW"
   #wait
done
