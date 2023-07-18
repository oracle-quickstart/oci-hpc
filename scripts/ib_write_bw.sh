#!/bin/bash
#ib_write_bw.sh
#This script can be used to check ib_write_bw between two gpu nodes in the cluster.
#Currently supported shapes are BM.GPU.B4.8,BM.GPU.A100-v2.8,BM.GPU4.8
#If cuda is installed on the node, script execution will recompile perftest with cuda.

dis_help()
{
   echo
   echo "Usage:"
   echo
   echo "./ib_write_bw_gpu.sh -s <server> -n <node> -c y"
   echo 
   echo "Options:"
   echo "s     Server hostname"
   echo "n     Client hostname."
   echo "c     Enable cuda(Disabled by default)"
   echo "h     Print this help."
   echo
   echo "Logs are stored at /tmp/logs"
   echo
   echo "Supported shapes: BM.GPU.B4.8,BM.GPU.A100-v2.8,BM.GPU4.8"
   echo
}

#Exit if no arguments passed
if [ "$#" -eq 0 ]
then
    dis_help
    exit 1
fi

#Display options
while getopts "s:n:c:h" option
do
    case $option in
        s) server=${OPTARG};;
        n) client=${OPTARG};;
        c) cuda=${OPTARG};;
        h) dis_help
	   exit;;
       \?) # Invalid option
           echo "Error: Invalid option"
           exit;;
    esac
done

#Set variables
cuda_path=`ssh $server /usr/sbin/alternatives --list|grep cuda | awk -F" " '{print $3}'|tail -1`/targets/x86_64-linux/include/cuda.h
server_ip=`grep $server /etc/hosts |grep -v rdma|awk '{print $1}'`
logdir=/tmp/logs/ib_bw/`date +%F-%H`
outdir=/tmp/ib_bw/

#Check node shape
shape=`ssh $server 'curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape'`
if [ "$shape" == \"BM.GPU.B4.8\" ] || [ "$shape" == \"BM.GPU.A100-v2.8\" ] || [ "$shape" == \"BM.GPU4.8\" ];
then
echo
echo "Shape: $shape"
echo "Server: $server"
echo "Client: $client"
echo "Cuda: $cuda"
else
  echo
  echo "Shape $shape is not supported by this script"
  dis_help
exit
fi

#Set interface to be skipped based on node shape
if [ "$shape" == \"BM.GPU.B4.8\" ] || [ "$shape" == \"BM.GPU.A100-v2.8\" ]
then
skip_if=mlx5_0
  elif [ "$shape" == \"BM.GPU4.8\" ]
  then
  skip_if=mlx5_4
fi

#Check active interfaces
echo
printf "Checking interfaces...\n"
srv_if_count=`ssh $server ibv_devinfo |egrep "hca_id|state"|tac|sed '/PORT_DOWN/I,+1d'|tac|sed -e '/PORT_ACTIVE/d'|awk -F: '{print $2}'|sed 's/[[:space:]]//g'|sort -t _ -k2.2|grep -v $skip_if|wc -l`
client_if_count=`ssh $client ibv_devinfo |egrep "hca_id|state"|tac|sed '/PORT_DOWN/I,+1d'|tac|sed -e '/PORT_ACTIVE/d'|awk -F: '{print $2}'|sed 's/[[:space:]]//g'|sort -t _ -k2.2|grep -v $skip_if|wc -l`

if [ "$srv_if_count" != "$client_if_count" ]
then
  echo
  echo "Active interfaces are different on both nodes. Please fix it before running this script"
  echo "Interface count on server: $srv_if_count"
  echo "Interface count on client: $client_if_count"
  exit 1
fi

#Generate ansible playbook
if [ "$cuda" == "y" ] || [ "$cuda" == "yes" ];
then
cat > /tmp/ib_bw_gpu.yml << EOF
---
- hosts: all
  become: true
  tasks:
    - name: check cuda
      stat: 
        path: $cuda_path
      register: cuda_data

    - block:
        - name: yum remove perftest
          yum:
            name: perftest
            state: absent

        - name: Git checkout perftest
          ansible.builtin.git:
            repo: 'https://github.com/linux-rdma/perftest.git'
            dest: /tmp/perftest

        - name: Run autogen.sh
          ansible.builtin.shell: /tmp/perftest/autogen.sh 
          args:
            chdir: /tmp/perftest
        
        - name: Run configure
          ansible.builtin.shell: ./configure CUDA_H_PATH=$cuda_path
          args:
            chdir: /tmp/perftest

        - name: Build 'all' target with extra arguments
          make:
            chdir: /tmp/perftest
            target: all

        - name: Copy files
          shell: cp /tmp/perftest/ib_* /usr/bin
      when: 
        - use_cuda is defined
        - use_cuda == "yes" or use_cuda == "y"
        - cuda_data.stat.exists
EOF

#Create ansible inventory
cat > /tmp/inventory << EOF
$server
$client
EOF
ansible-playbook /tmp/ib_bw_gpu.yml -i /tmp/inventory -e "use_cuda=$cuda"
fi

#Generate server script
cat > /tmp/ib_server.sh << 'EOF'
#! /bin/bash

out_dir=/tmp/ib_bw
mkdir -p $out_dir
shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.B4.8\" ] || [ $shape == \"BM.GPU.A100-v2.8\" ]
then
skip_if=mlx5_0
  elif [ $shape == \"BM.GPU4.8\" ]
  then
  skip_if=mlx5_4
fi
for interface in `ibv_devinfo |egrep "hca_id|state"|tac|sed '/PORT_DOWN/I,+1d'|tac|sed -e '/PORT_ACTIVE/d'|awk -F: '{print $2}'|sed 's/[[:space:]]//g'|sort -t _ -k2.2|grep -v $skip_if`
do
echo
echo "Server Interface: $interface"
echo
ib_write_bw -d $interface -a -F &> $out_dir/ib_server-$interface
sleep 10
done
EOF

#Generate client script
cat > /tmp/ib_client.sh << 'EOF'
#! /bin/bash

out_dir=/tmp/ib_bw
mkdir -p $out_dir
#interfaces
shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
if [ $shape == \"BM.GPU.B4.8\" ] || [ $shape == \"BM.GPU.A100-v2.8\" ]
then
skip_if=mlx5_0
  elif [ $shape == \"BM.GPU4.8\" ]
  then
  skip_if=mlx5_4
fi
for interface in `ibv_devinfo |egrep "hca_id|state"|tac|sed '/PORT_DOWN/I,+1d'|tac|sed -e '/PORT_ACTIVE/d'|awk -F: '{print $2}'|sed 's/[[:space:]]//g'|sort -t _ -k2.2|grep -v $skip_if`
do
ib_write_bw -d $interface -F $server_ip -D 10 --cpu_util --report_gbits &> $out_dir/ib_client-$interface
cat $out_dir/ib_client-$interface
sleep 15
done
EOF

#Update server ip in ib_client.sh
sed -i "/#interfaces/a server_ip=$server_ip" /tmp/ib_client.sh 
chmod +x /tmp/ib_server.sh /tmp/ib_client.sh

#Update scripts to use cuda if selected
if [ "$cuda" == "yes" ];
then
  if [ -f /usr/local/$cuda_path/targets/x86_64-linux/include/cuda.h ];
  then
    sed -i 's/ib_write_bw.*/ib_write_bw -d $interface --use_cuda=0 -F > $out_dir\/ib_server-$interface/g' /tmp/ib_server.sh
    sed -i 's/ib_write_bw.*/ib_write_bw -d $interface --use_cuda=0 -D 10 -I 0 $server_ip --cpu_util --report_gbits/g' /tmp/ib_client.sh
  fi
fi
echo 

#Copy and run scripts
scp /tmp/ib_server.sh $server:/tmp
scp /tmp/ib_client.sh $client:/tmp
ssh $server "/tmp/ib_server.sh" &
ssh $client "/tmp/ib_client.sh"

#Sync results to bastion
mkdir -p $logdir
rsync -a opc@$client:$outdir $logdir

#Generate test summary
echo 
echo "************** Test Summary **************"
for i in `ls -ltr $logdir | awk -F" " '{print $9}'|awk -F- '{print $2}'`; do 
echo 
echo Server interface: $i | tee -a /tmp/ib_write_bw_log.txt
echo
grep -A2 MsgRate $logdir/ib_client-$i | tee -a /tmp/ib_write_bw_log.txt
done