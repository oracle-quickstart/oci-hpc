#!/bin/bash

# Hostfile containing the name of all the hosts should be passed as an argument to this script
if [ $# -ne 1 ]; then
   echo "Usage: $0 <hostlist>"
   exit -1
fi

if [ ! -f $1 ]; then
   echo "$1 does not exist"
   exit -2
fi

declare all_hosts_file=$1

# Get absolute path of current directory
declare -x ROOT_DIR=`pwd`

# GPU Shape
if [[ $(hostname) -eq $(head -1 ${all_hosts_file}) ]]; then
   declare gpu_shape=`curl -sH "Authorization: Bearer Oracle" -L http://169.254.169.254/opc/v2/instance/ | jq .shape`
else
   declare gpu_hostname=$(head -1 ${all_hosts_file})
   declare gpu_shape=$(ssh ${gpu_hostname} curl -sH \"Authorization: Bearer Oracle\" -L http://169.254.169.254/opc/v2/instance/ | jq .shape)
fi

# NCCL script path and it's parameters
if [ ${gpu_shape} == \"BM.GPU.B4.8\" ] || [ ${gpu_shape} == \"BM.GPU.A100-v2.8\" ]; then
   declare nccl_script="/opt/oci-hpc/samples/gpu/nccl_run_allreduce.sh"
   declare nccl_gpus_per_hostpair="16"
   declare nccl_run_count="1"
   # Minimum acceptable bandwidth for the shape to filter out unhealthy instances
   declare avg_baseline_bw="160"
elif [ ${gpu_shape} == \"BM.GPU.H100.8\" ]; then
   declare nccl_script="/opt/oci-hpc/samples/gpu/nccl_run_allreduce_H100_200.sh"
   declare nccl_gpus_per_hostpair="16"
   declare nccl_run_count="1"
   # Minimum acceptable bandwidth for the shape to filter out unhealthy instances
   declare avg_baseline_bw="370"
fi

# NCCL log file name
declare nccl_log_file_name="nccl_run_allreduce.sh.log"

# Load MPI environment
module load mpi/openmpi/4.1.4-gcc

# Variables for trapping and exiting the script in case any host is unavailable
trap "exit 1" TERM
declare -x TOP_PID=$$

# Define host files created by script
declare unknownStatus_hosts="unknownStatus_hosts.txt"
declare retest_host_file="retest_hosts.txt"
declare unhealthy_host_file="failed_hosts.txt"
declare healthy_host_file="passed_hosts.txt"
declare hostpair_file_prefix="hostpair_"
declare backup_folder="backup"

# Absolute path of Linux programs
declare split_exe='/usr/bin/split'
declare ls_exe='/usr/bin/ls'
declare rm_exe='/usr/bin/rm'
declare wc_exe='/usr/bin/wc'
declare mv_exe='/usr/bin/mv'
declare cat_exe='/usr/bin/cat'
declare mkdir_exe='/usr/bin/mkdir'
declare find_exe='/usr/bin/find'

# Remove existing log files
function cleanAll() {

        # Create backup folder
        if [ ! -d ${backup_folder} ]; then
                ${mkdir_exe} ${backup_folder}
        fi

        # Backup existing host pair files, if any
        local hp_files=$(${find_exe} . -maxdepth 1 -name "${hostpair_file_prefix}*")
        for hp_file in ${hp_files}
           do
               ${rm_exe} -rv ${hp_file}
           done

        # Backup existing restest file, if there's one
        if [ -f ${unknownStatus_hosts} ]; then
                ${mv_exe} ${unknownStatus_hosts} ${backup_folder}/${unknownStatus_hosts}.$$
        fi

        # Backup existing failed host file, if there's one
        if [ -f ${retest_host_file} ]; then
                ${mv_exe} ${retest_host_file} ${backup_folder}/${retest_host_file}.$$
        fi

        # Backup existing healthy host file, if there's one
        if [ -f ${healthy_host_file} ]; then
                ${mv_exe} ${healthy_host_file} ${backup_folder}/${healthy_host_file}.$$
        fi

        # Backup existing unhealthy host file, if there's one
        if [ -f ${unhealthy_host_file} ]; then
                ${mv_exe} ${unhealthy_host_file} ${backup_folder}/${unhealthy_host_file}.$$
        fi
}

# Define function for creating files with host pairs
function createHostPairFile() {

        # Minimum count of arguments
        if [ $# -lt 1 ]; then
           echo "Error: Requires at least 1 arguments!"
           return 1
        fi

        while IFS= read -r line; do
           ssh -o ConnectTimeout=5 $line "exit" < /dev/null
           if [[ "$?" -ne "0" ]]; then
              echo "Host "${line}" is unreachanble"
              echo "Either fix it, or remove it from the list of host file"
              kill -s TERM ${TOP_PID}
           fi
        done < $1

        ${split_exe} -l 2 -a 3 -d --additional-suffix=.txt $1 ${hostpair_file_prefix}
}

#
function run_nccl_script() {

        # rundir list and it's index
        declare -a rundir_list
        i=0

        local host_file_name='hosts.txt'

        for hp_file in $1
        do
            hp_file=$(echo $hp_file | tr -d '\n')
            local rundir=${2}_$(echo ${hp_file} | cut -d'_' -f2 | cut -d'.' -f1)
            rundir_list[i]=${rundir}
            i+=1

            if [ -d ${rundir} ]; then
                    if [ -d ${backup_folder} ]; then
                       ${mv_exe} ${rundir} ${backup_folder}/${rundir}.$$
                    else
                       ${mkdir_exe} ${backup_folder}
                       ${mv_exe} ${rundir} ${backup_folder}/${rundir}.$$
                    fi
            fi

        ${mkdir_exe} $rundir
        ${mv_exe} ${hp_file} $rundir/${host_file_name}
        cd ${rundir}

        if [ "$2" == "test" ]; then
           echo "Run Dir: $(realpath ${rundir})"
           timeout 120 ${nccl_script} ${nccl_run_count} ${host_file_name} ${nccl_gpus_per_hostpair} &
           sleep 1
        elif [ "$2" == "retest" ]; then
           echo "Run Dir: $(realpath ${rundir})"
           timeout 120 ${nccl_script} ${nccl_run_count} ${host_file_name} ${nccl_gpus_per_hostpair}
        fi

        cd ${ROOT_DIR}
        done

        wait

        for rdir in ${rundir_list[@]}
        do
        local reported_bw=$(${cat_exe} ${rdir}/${nccl_log_file_name} | grep "# Avg bus bandwidth" | cut -d':' -f2 | sort -n -r | head -1 | tr -d "[:blank:]")

        # Check if reported bandwidth contains a valid value
        if [[ -z ${reported_bw} ]]; then
           local rounded_bw=0
        else
           local rounded_bw=`echo $reported_bw | awk '{printf("%d\n",$1 + 0.5)}'`
        fi

        #echo "REPORTED BW: ${reported_bw}"

        if [ "$2" == "test" ]; then
           if [[ "${rounded_bw}" -lt "${avg_baseline_bw}" ]] || [[ -z "${reported_bw}" ]]; then
              $(${cat_exe} ${rdir}/${host_file_name} >> ${ROOT_DIR}/${unknownStatus_hosts})
           elif [[ "${rounded_bw}" -ge "${avg_baseline_bw}" ]]; then
              $(${cat_exe} ${rdir}/${host_file_name} >> ${ROOT_DIR}/${healthy_host_file})
           fi
        elif [ "$2" == "retest" ]; then
           if [[ "${rounded_bw}" -lt "${avg_baseline_bw}" ]] || [[ -z "${reported_bw}" ]]; then
                   echo "$(tail -1 ${rdir}/${host_file_name}), BW: ${reported_bw}" >> ${ROOT_DIR}/${unhealthy_host_file}
           elif [[ "${rounded_bw}" -ge "${avg_baseline_bw}" ]]; then
              tail -1 ${rdir}/${host_file_name} >> ${ROOT_DIR}/${healthy_host_file}
           fi
        fi
        done
}

function printSummary() {

        if [[ -f $1 ]]; then
                echo "List of good hosts:"
                echo ""
                ${cat_exe} $1
                echo ""
        fi

        if [[ -f $2 ]]; then
                echo "List of hosts with bandwidth below the defined baseline:"
                echo ""
                ${cat_exe} $2
                echo ""
        fi

}

# Check if NCCL script exists
if [[ -f ${nccl_script} && -x ${nccl_script} ]]; then
   echo "NCCL script: ${nccl_script}"
else
   echo "Check if file ${nccl_script} exists and is an executable"
fi

# Remove existing log files
cleanAll

# Count total host file entries in the all_hosts_file
total_host_count=$(${cat_exe} ${all_hosts_file} | wc -l)
even_count_check=`expr $total_host_count % 2`

# The all_hosts file should have atleast two distinct entries and the overall entries should be even
if [[ ${total_host_count} -lt 2 ]]; then
   echo "Please check the hostfile."
   echo "It should contain atleast two distinct host entries"
   exit "1"
elif [[ ${even_count_check} -ne 0 ]]; then
   ${mv_exe} ${all_hosts_file} ${all_hosts_file}.$$
   head -n $((${total_host_count} -1)) ${all_hosts_file}.$$ > ${all_hosts_file}
   tail -n -1 ${all_hosts_file}.$$ > ${unknownStatus_hosts}
   # Create host pair files
   createHostPairFile $all_hosts_file
   # Revert the hostfile back to original state if it's temporary copy was created to handle odd entries
   ${mv_exe} ${all_hosts_file}.$$ ${all_hosts_file}
elif [[ ${even_count_check} -eq 0 ]]; then
   # Create host pair files
   createHostPairFile $all_hosts_file
fi

# Get the list of host pair files
declare -a host_pair_files=$(ls -l ${hostpair_file_prefix}* | awk '{print $9}')

# Remove host pair files with duplicate entries
for hp_file in ${host_pair_files}
do
    if [[ $(${cat_exe} ${hp_file} | uniq | wc -l) -lt 2 ]]; then
       $(${cat_exe} ${ROOT_DIR}/${hp_file} | uniq >> ${unknownStatus_hosts})
       ${rm_exe} ${hp_file}
    fi
done

# Run NCCL for every pair of host created
run_nccl_script "${host_pair_files[@]}" test

if [[ -f ${unknownStatus_hosts} ]] && [[ -f ${healthy_host_file} ]]; then

   # Create host pair files for retesting
   declare known_good_host=$(head -n 1 ${healthy_host_file})

   # Move the restest file, if one exists and create afresh
   if [[ -f ${retest_host_file} ]]; then
      ${mv_exe} ${retest_host_file} ${backup_folder}/${retest_host_file}.$$
   fi

   for fh in $(cat ${unknownStatus_hosts})
   do
     echo ${known_good_host} >> ${retest_host_file}
     echo ${fh} >> ${retest_host_file}
   done

   createHostPairFile ${retest_host_file}
   # Get the list of host pair files created for running the test again on the instances that reported lower average bw
   declare -a host_pair_files=$(ls -l ${hostpair_file_prefix}* | awk '{print $9}')
   run_nccl_script "${host_pair_files[@]}" retest
elif [[ -f ${unknownStatus_hosts} ]] && [[ ! -f ${healthy_host_file} ]]; then
   echo "Require at least one good known host to \"retest\" instances that failed first round of test"
fi

# Print Summary
printSummary ${healthy_host_file} ${unhealthy_host_file}
