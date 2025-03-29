#!/bin/bash

# run ib_write_lat between two nodes
# If on bastion: ./ib_write_lat.sh <server> <client>
# If on one compute node:  ./ib_write_lat.sh <server>

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

cmd_base="/usr/bin/ib_write_lat -F -x 3 -s 8 -n 10000"

for Dev in $HCA; do
    echo -e "$Server $Client $Dev \c"

    # Start server in background, redirect output to /dev/null
    ssh $Server exec $cmd_base -d "$Dev" > /dev/null 2>&1 &

    # Wait briefly for server to start listening
    sleep 1

    # Run client, extract latency for 8-byte messages, 10000 iterations
    LATENCY=$(ssh $Client $cmd_base -d "$Dev" "$Server" | grep "^ 8       10000" | awk '{print $6}')

    # Output the latency
    echo "$LATENCY"

    # Optional: Wait for server process to finish (if needed)
    # wait
done
