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
mp=$(ssh "$Server" 'curl -fsSH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/host/rdmaFabricData/planes 2>/dev/null || echo 1')

[[ "$mp" =~ ^[0-9]+$ ]] || mp=1

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
  BM.GPU.B300.8|BM.GPU.B300.HS.8)
    if [ "$mp" == "4" ]; then
      HCA_ARRAY=(rdma_vf_rail0 rdma_vf_rail1 rdma_vf_rail2 rdma_vf_rail3
                 rdma_vf_rail4 rdma_vf_rail5 rdma_vf_rail6 rdma_vf_rail7)
    else
      HCA_ARRAY=(mlx5_0  mlx5_1  mlx5_7  mlx5_8
                 mlx5_9  mlx5_10 mlx5_11 mlx5_12
                 mlx5_13 mlx5_14 mlx5_16 mlx5_17
                 mlx5_18 mlx5_19 mlx5_20 mlx5_21)
    fi
    ;;
  BM.GPU.GB200.4)
    HCA_ARRAY=(mlx5_0  mlx5_1  mlx5_3  mlx5_4)
    ;;
  BM.GPU.GB200-v2.4)
    HCA_ARRAY=(mlx5_0  mlx5_1  mlx5_3  mlx5_4)
    ;;
  BM.GPU.GB200-v3.4|BM.GPU.GB300.4)
    if [[ "$mp" == "4" ]]; then
      HCA_ARRAY=(rdma_vf_rail0 rdma_vf_rail1 rdma_vf_rail2 rdma_vf_rail3)
    else
      HCA_ARRAY=(mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_5 mlx5_6 mlx5_7 mlx5_8)
    fi
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

get_vrf_for_device() {
  case "$1" in
    rdma_vf_rail0) echo "vrf_r0" ;;
    rdma_vf_rail1) echo "vrf_r1" ;;
    rdma_vf_rail2) echo "vrf_r2" ;;
    rdma_vf_rail3) echo "vrf_r3" ;;
    rdma_vf_rail4) echo "vrf_r4" ;;
    rdma_vf_rail5) echo "vrf_r5" ;;
    rdma_vf_rail6) echo "vrf_r6" ;;
    rdma_vf_rail7) echo "vrf_r7" ;;
  esac
}

get_port_for_device() {
  case "$1" in
    rdma_vf_rail0) echo "18001" ;;
    rdma_vf_rail1) echo "18002" ;;
    rdma_vf_rail2) echo "18003" ;;
    rdma_vf_rail3) echo "18004" ;;
    rdma_vf_rail4) echo "18005" ;;
    rdma_vf_rail5) echo "18006" ;;
    rdma_vf_rail6) echo "18007" ;;
    rdma_vf_rail7) echo "18008" ;;
  esac
}

get_cuda_bus_for_device() {
  if [ "$shape" == "BM.GPU.B300.8" ] || [ "$shape" == "BM.GPU.B300.HS.8" ]; then
    case "$1" in
      rdma_vf_rail0) echo "00000014:00.0" ;;
      rdma_vf_rail1) echo "00000032:00.0" ;;
      rdma_vf_rail2) echo "00000049:00.0" ;;
      rdma_vf_rail3) echo "00000060:00.0" ;;
      rdma_vf_rail4) echo "0000008E:00.0" ;;
      rdma_vf_rail5) echo "000000AD:00.0" ;;
      rdma_vf_rail6) echo "000000C5:00.0" ;;
      rdma_vf_rail7) echo "000000DD:00.0" ;;
    esac
    return
  fi

  case "$1" in
    rdma_vf_rail0) echo "00000009:06:00.0" ;;
    rdma_vf_rail1) echo "00000008:06:00.0" ;;
    rdma_vf_rail2) echo "00000019:06:00.0" ;;
    rdma_vf_rail3) echo "00000018:06:00.0" ;;
  esac
}

get_cmd_for_device() {
  local dev=$1
  local vrf
  vrf=$(get_vrf_for_device "$dev")
  if [ -n "$vrf" ]; then
    echo "sudo ip vrf exec $vrf $cmd_base -d $dev -p $(get_port_for_device "$dev")"
  else
    echo "$cmd_base -d $dev"
  fi
}

get_ipv6_for_device() {
  local host=$1
  local dev=$2
  ssh "$host" "dev=$dev; netdev=\$dev; if [ -d /sys/class/infiniband/\$dev/device/net ]; then found=\$(ls /sys/class/infiniband/\$dev/device/net 2>/dev/null | head -n 1); [ -n \"\$found\" ] && netdev=\$found; fi; ip -6 -o addr show dev \"\$netdev\" scope global 2>/dev/null | awk '{split(\$4,a,\"/\"); print a[1]; exit}'"
}

# Iterate over each HCA; the index determines the NUMA node.
for idx in "${!HCA_ARRAY[@]}"; do
  Dev="${HCA_ARRAY[$idx]}"
  vrf=$(get_vrf_for_device "$Dev")

  # Decide which NUMA node (0 or 1) based on index < half
  if (( idx < half )); then
    numa_node=0
  else
    numa_node=1
  fi

  if [ -n "$vrf" ]; then
    cmd=$(get_cmd_for_device "$Dev")
    server_ipv6=$(get_ipv6_for_device "$Server" "$Dev")
    if [ -z "$server_ipv6" ]; then
      echo "$Server $Client $Dev Could not find IPv6 address"
      continue
    fi
    server_cmd="$cmd --ipv6-addr"
    client_cmd="$cmd --ipv6-addr $server_ipv6"
    echo -n "$Server $Client $Dev: "
  else
    server_cmd="numactl -N $numa_node $cmd_base -d $Dev"
    client_cmd="numactl -N $numa_node $cmd_base -d $Dev $Server"
    echo -n "$Server $Client $Dev → NUMA $numa_node: "
  fi

  # Start server side in background (no output)
  ssh "$Server" "exec $server_cmd" \
    > /dev/null 2>&1 &

  # Give server 1 second to start listening
  sleep 1

  # On the client side, bind to the same NUMA node or rail VRF
  LATENCY=$(ssh "$Client" "$client_cmd" \
               | grep '^ 8[[:space:]]\+10000' \
               | awk '{print $6}')

  # Print just the raw latency number
  echo "$LATENCY"

  # (Optional) If you want to wait for the server process to finish before moving on,
  # uncomment the next line. Otherwise, backgrounded server will be reaped when done.
  # wait
done
