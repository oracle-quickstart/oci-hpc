#!/bin/bash

# run ib_write_lat between two nodes
# Usage:
#   If on bastion:    ./ib_write_lat.sh <server> <client>
#   If on one compute node:  ./ib_write_lat.sh <server>

Server=$1
Client=${2:-localhost}

# Default Dev is not needed here because we will override it in the loop
# Dev=${3:-mlx5_17}

# Fetch the shape string from the given Server via the metadata service
shape=$(ssh "$Server" 'curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape')

# Build a Bash array called HCA_ARRAY based on the shape
HCA_ARRAY=()
case "$shape" in
  BM.GPU4.8)
    # 16 HCAs total → split into two arrays of 8 each
    HCA_ARRAY=(mlx5_0  mlx5_1  mlx5_2  mlx5_3
               mlx5_6  mlx5_7  mlx5_8  mlx5_9
               mlx5_10 mlx5_11 mlx5_12 mlx5_13
               mlx5_14 mlx5_15 mlx5_16 mlx5_17)
    ;;
  BM.GPU.A100-v2.8)
    HCA_ARRAY=(mlx5_1  mlx5_2  mlx5_3  mlx5_4
               mlx5_5  mlx5_6  mlx5_7  mlx5_8
               mlx5_9  mlx5_10 mlx5_11 mlx5_12
               mlx5_14 mlx5_15 mlx5_16 mlx5_17)
    ;;
  BM.GPU.H100.8)
    HCA_ARRAY=(mlx5_0  mlx5_1  mlx5_3  mlx5_4
               mlx5_5  mlx5_6  mlx5_7  mlx5_8
               mlx5_9  mlx5_10 mlx5_12 mlx5_13
               mlx5_14 mlx5_15 mlx5_16 mlx5_17)
    ;;
  BM.GPU.H200.8|BM.GPU.B200.8)
    # For both H200.8 and B200.8 shapes, the same set of 8 HCAs
    HCA_ARRAY=(mlx5_0  mlx5_3  mlx5_4  mlx5_5
               mlx5_6  mlx5_9  mlx5_10 mlx5_11)
    ;;
  BM.GPU.GB200.4)
    HCA_ARRAY=(mlx5_0  mlx5_1  mlx5_3  mlx5_4)
    ;;
  BM.GPU.GB200-v2.4)
    HCA_ARRAY=(mlx5_0  mlx5_1  mlx5_3  mlx5_4)
    ;;
  BM.GPU.GB200-v3.4)
    HCA_ARRAY=(mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_5 mlx5_6 mlx5_7 mlx5_8)
    ;;    
  BM.GPU.GB300.4)
    HCA_ARRAY=(mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_5 mlx5_6 mlx5_7 mlx5_8)
    ;;
  BM.GPU.B4.8)
    HCA_ARRAY=(mlx5_1  mlx5_2  mlx5_3  mlx5_4
               mlx5_5  mlx5_6  mlx5_7  mlx5_8
               mlx5_9  mlx5_10 mlx5_11 mlx5_12
               mlx5_14 mlx5_15 mlx5_16 mlx5_17)
    ;;
  BM.Optimized3.36)
    HCA_ARRAY=(mlx5_2)
    ;;
  *)
    echo "Error: Shape '$shape' is not supported."
    exit 1
    ;;
esac

# Compute where to split the array in half (integer division).
# For N HCAs, the first N/2 go to NUMA 0; the remaining go to NUMA 1.
total_hcas=${#HCA_ARRAY[@]}
half=$(( total_hcas / 2 ))

cmd_base="/usr/bin/ib_write_lat -F -x 3 -s 8 -n 10000"

# Iterate over each HCA; the index determines the NUMA node.
for idx in "${!HCA_ARRAY[@]}"; do
  Dev="${HCA_ARRAY[$idx]}"

  # Decide which NUMA node (0 or 1) based on index < half
  if (( idx < half )); then
    numa_node=0
  else
    numa_node=1
  fi

  echo -n "$Server $Client $Dev → NUMA $numa_node: "

  # Start server side in background (no output)
  ssh "$Server" "numactl -N $numa_node $cmd_base -d $Dev" \
    > /dev/null 2>&1 &

  # Give server 1 second to start listening
  sleep 1

  # On the client side, bind to the same NUMA node
  LATENCY=$(ssh "$Client" "numactl -N $numa_node $cmd_base -d $Dev $Server" \
               | grep '^ 8[[:space:]]\+10000' \
               | awk '{print $6}')

  # Print just the raw latency number
  echo "$LATENCY"

  # (Optional) If you want to wait for the server process to finish before moving on,
  # uncomment the next line. Otherwise, backgrounded server will be reaped when done.
  # wait
done
