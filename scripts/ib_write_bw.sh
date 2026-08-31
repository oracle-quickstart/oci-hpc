#!/bin/bash
set -uo pipefail

# run ib_write_bw between two nodes
# If on bastion: ./ib_write_bw.sh <server> <client>
# If on one compute node:  ./ib_write_bw.sh <server>

Server=$1
Client=${2:-localhost}
Dev=${3:-mlx5_17}
Duration=${IB_WRITE_BW_DURATION:-10}
shape=$(ssh "$Server" 'curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq -r .shape')
mp=$(ssh "$Server" 'curl -fsSH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/host/rdmaFabricData/planes 2>/dev/null || echo 1')

[[ "$mp" =~ ^[0-9]+$ ]] || mp=1

if [ "$shape" == "BM.GPU4.8" ]; then
   HCA="mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_13 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.GPU.A100-v2.8" ]; then
   HCA="mlx5_1 mlx5_2 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.GPU.H100.8" ]; then
   HCA="mlx5_0 mlx5_1 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_12 mlx5_13 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.GPU.H200.8" ]; then
   HCA="mlx5_0 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_9 mlx5_10 mlx5_11"
elif [ "$shape" == "BM.GPU.B200.8" ]; then
   HCA="mlx5_0 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_9 mlx5_10 mlx5_11"
elif [ "$shape" == "BM.GPU.B300.8" ] || [ "$shape" == "BM.GPU.B300.HS.8" ]; then
  if [ "$mp" == "4" ]; then
    HCA="rdma_vf_rail0 rdma_vf_rail1 rdma_vf_rail2 rdma_vf_rail3 rdma_vf_rail4 rdma_vf_rail5 rdma_vf_rail6 rdma_vf_rail7"
  else
    HCA="mlx5_0 mlx5_1 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_13 mlx5_14 mlx5_16 mlx5_17 mlx5_18 mlx5_19 mlx5_20 mlx5_21"
  fi
elif [ "$shape" == "BM.GPU.B300.HS.8" ]; then
  if [ "$mp" == "4" ]; then
    HCA="rdma_vf_rail0 rdma_vf_rail1 rdma_vf_rail2 rdma_vf_rail3 rdma_vf_rail4 rdma_vf_rail5 rdma_vf_rail6 rdma_vf_rail7"
  else
    HCA="mlx5_0 mlx5_1 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_13 mlx5_14 mlx5_16 mlx5_17 mlx5_18 mlx5_19 mlx5_20 mlx5_21"
  fi
elif [ "$shape" == "BM.GPU.GB200.4" ]; then
   HCA="mlx5_0 mlx5_1 mlx5_3 mlx5_4"
elif [ "$shape" == "BM.GPU.GB200-v2.4" ]; then
   HCA="mlx5_0 mlx5_1 mlx5_3 mlx5_4"
elif [ "$shape" == "BM.GPU.GB200-v3.4" ]; then
  if [ "$mp" == "4" ]; then
    HCA="rdma_vf_rail0 rdma_vf_rail1 rdma_vf_rail2 rdma_vf_rail3"
  else
    HCA="mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_5 mlx5_6 mlx5_7 mlx5_8"
  fi
elif [ "$shape" == "BM.GPU.GB300.4" ]; then
  if [ "$mp" == "4" ]; then
    HCA="rdma_vf_rail0 rdma_vf_rail1 rdma_vf_rail2 rdma_vf_rail3"
  else
   HCA="mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_5 mlx5_6 mlx5_7 mlx5_8"
  fi
elif [ "$shape" == "BM.GPU.B4.8" ]; then
   HCA="mlx5_1 mlx5_2 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_7 mlx5_8 mlx5_9 mlx5_10 mlx5_11 mlx5_12 mlx5_14 mlx5_15 mlx5_16 mlx5_17"
elif [ "$shape" == "BM.Optimized3.36" ]; then
   HCA="mlx5_2"
elif [ "$shape" == "BM.GPU.MI355X-v1.8" ]; then
   HCA="mlx5_0 mlx5_1 mlx5_2 mlx5_3 mlx5_4 mlx5_5 mlx5_6 mlx5_7"
else
   echo "Shape $shape not supported" >&2
   exit 1
fi
cmd_base="/usr/bin/ib_write_bw -F -q 2 -x 3 --report_gbits -D $Duration"

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

   if [ "$shape" == "BM.GPU.B300.HS.8" ]; then
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

get_cuda_dma_for_device() {
   if [ "$shape" == "BM.GPU.B300.8" ] || [ "$shape" == "BM.GPU.B300.HS.8" ]; then
      echo "--use_cuda_dmabuf"
   else
      echo "--use_cuda_dmabuf --use_data_direct"
   fi
}

get_cmd_for_device() {
   local dev=$1
   local vrf
   vrf=$(get_vrf_for_device "$dev")
   if [ -n "$vrf" ]; then
      echo "sudo ip vrf exec $vrf $cmd_base --use_cuda_bus_id=$(get_cuda_bus_for_device "$dev") $(get_cuda_dma_for_device) -d $dev -p $(get_port_for_device "$dev")"
   else
      echo "$cmd_base -d $dev"
   fi
}

get_ipv6_for_device() {
   local host=$1
   local dev=$2
   ssh "$host" "dev=$dev; netdev=\$dev; if [ -d /sys/class/infiniband/\$dev/device/net ]; then found=\$(ls /sys/class/infiniband/\$dev/device/net 2>/dev/null | head -n 1); [ -n \"\$found\" ] && netdev=\$found; fi; ip -6 -o addr show dev \"\$netdev\" scope global 2>/dev/null | awk '{split(\$4,a,\"/\"); print a[1]; exit}'"
}

for Dev in $HCA; do
   vrf=$(get_vrf_for_device "$Dev")
   cmd=$(get_cmd_for_device "$Dev")
   server_cmd=$cmd
   client_cmd="$cmd $Server"

   if [ -n "$vrf" ]; then
      server_ipv6=$(get_ipv6_for_device "$Server" "$Dev")
      if [ -z "$server_ipv6" ]; then
         echo "$Server $Client $Dev Could not find IPv6 address"
         continue
      fi
      server_cmd="$cmd --ipv6-addr"
      client_cmd="$cmd --ipv6-addr $server_ipv6"
   fi

   echo -e "$Server $Client $Dev \c"
   ssh "$Server" "exec $server_cmd" > /dev/null 2>&1 &
   # make sure the server start listening before client make requests
   sleep 1
   BW=$(ssh "$Client" "$client_cmd" | grep 65536 | awk '{print $4}')
   #BW=`ssh $Client $cmd_base -d $Dev $Server `
   echo "$BW"
   #wait
done
