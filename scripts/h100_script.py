import os
from datetime import datetime
import argparse
import subprocess
import sys


def getDateTime():
    # datetime object containing current date and time
    now = datetime.now()
    dt_string = now.strftime("%m%d%Y%H%M%S")
    return dt_string


# create directory to hold results
def createDir():
    # directory name
    directory = str("/tmp/" + getDateTime()) 
    try:
        os.mkdir(directory)
    except OSError as error:
        print(error)
        sys.exit(-1)
    return directory


# change ownership of all files to user so that the files can be copied
def changeOwner(path):
    username = os.getlogin()
    cmd = f'sudo chown -R {username}:{username} {path}'
    run_cmd(cmd)


def getSshableNodes(hosts, path):
    hosts_file = open(hosts, "r")
    ssh_list = path + "/" + "sshable"
    not_ssh_list = path + "/" + "notsshable"
    sshable = open(ssh_list, "a")
    notsshable = open(not_ssh_list, "a")
    for line in hosts_file:
        host = line.split()
        host_value = host[0]
        cmd = f'ssh -o ConnectTimeout=10 {host_value} "cat /etc/os-release | grep PRETTY_NAME"'
        isSshable = run_cmd(cmd)
        if not isSshable:
            notsshable.write(host_value)
            notsshable.write("\n")
        elif 'PRETTY_NAME' in isSshable[0]:
            sshable.write(host_value)
            sshable.write("\n")
        else:
            notsshable.write(host_value)
            notsshable.write("\n")
    sshable.close()
    notsshable.close()
    hosts_file.close()
    return ssh_list


def run_cmd(cmd=None):
    """ Run command on shell"""
    try:
        results = subprocess.run(cmd, shell=True, executable='/bin/bash', stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, encoding='utf8')
        output = results.stdout.splitlines()
    except subprocess.CalledProcessError as e:
        print (f'Command {e.cmd} failed with error {e.returncode}')
        return e.returncode
    return output
    

# get interfaces that are Down
def ibdev(hosts, path):
    log_file = path + "/" + "ibdev2netdev"
    cmd = f'for i in $(cat {hosts}); do ssh $i "hostname; hostname -i; sudo dmidecode -s system-serial-number; ibdev2netdev | grep Down"; done > {log_file}'
    run_cmd(cmd)


# get EAP-FAILURE
def eapFailure(hosts, path):
    log_file = path + "/" + "eapfailure"
    cmd = f'for i in $(cat {hosts}); do ssh $i "hostname; hostname -i; sudo dmidecode -s system-serial-number; cat /var/log/syslog | grep "EAP-FAILURE""; done > {log_file}'
    run_cmd(cmd)


# get rdma links authentication
def rdmaAuth(hosts, path):
    log_file = path + "/" + "rdmaauth"
    hosts_file = open(hosts, "r")
    log_file = path + "/" + "rdmaauth"
    rdma_file = open(log_file, "a")
    for line in hosts_file:
        host = line.split()
        host_value = host[0]
        cmd = f'ssh {host_value} "hostname; hostname -i; sudo dmidecode -s system-serial-number"'
        output = run_cmd(cmd)
        for o in output:
            rdma_file.write(o)
            rdma_file.write("\n")
        cmd = f'ssh {host_value} \'for x in $(seq 0 15) ; do sudo wpa_cli -i rdma$x status | grep EAP ; done\''
        output = run_cmd(cmd)
        for o in output:
            rdma_file.write(o)
            rdma_file.write("\n")
    rdma_file.close()
    hosts_file.close()


# get logs for Link Flapping
def linksDown(hosts, path):
    log_file = path + "/" + "linkflapping"
    cmd = f'for i in $(cat {hosts}); do ssh $i "hostname; hostname -i; sudo dmidecode -s system-serial-number; cat /var/log/syslog | grep "Link " | tail -36"; done > {log_file}'
    run_cmd(cmd)


# Check any GPU fallen off the bus
def lspci(hosts, path):
    log_file = path + "/" + "lspci"
    cmd = f'for i in $(cat {hosts}); do ssh $i "hostname; hostname -i; sudo dmidecode -s system-serial-number; lspci | grep "rev ff""; done > {log_file}'
    run_cmd(cmd)


# Check for NVRM errors
def nvrm(hosts, path):
    log_file = path + "/" + "nvrm"
    cmd = f'for i in $(cat {hosts}); do ssh $i "hostname; hostname -i; sudo dmidecode -s system-serial-number; sudo dmesg | grep NVRM"; done > {log_file}'
    run_cmd(cmd)


# Check for Pending remaps
def pending(hosts, path):
    log_file = path + "/" + "pending_remaps"
    cmd = f'for i in $(cat {hosts}); do ssh $i "hostname; hostname -i; sudo dmidecode -s system-serial-number; nvidia-smi -q | grep "Pending                           : Yes""; done > {log_file}'
    run_cmd(cmd)


# Check for Remapping failures
def remapping(hosts, path):
    log_file = path + "/" + "remapping_failures"
    cmd = f'for i in $(cat {hosts}); do ssh $i "hostname; hostname -i; sudo dmidecode -s system-serial-number; nvidia-smi -q | grep "Remapping Failure Occurred        : Yes""; done > {log_file}'
    run_cmd(cmd)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description = 'Capture H100 troubleshooting data.')
    parser.add_argument('--hosts', help = "Provide a filepath that contains list of either IPs / hostnames one per line on which you want to run this script.", required = True)
    args = parser.parse_args()
    hosts = args.hosts
    if hosts is None:
        print("Hostfile is required. Please provide one and run again.")
        sys.exit(-1)
    else:
        path = createDir()
        changeOwner(path)
        ssh_hosts = getSshableNodes(hosts, path)
        ibdev(ssh_hosts, path)
        eapFailure(ssh_hosts, path)
        rdmaAuth(ssh_hosts, path)
        linksDown(ssh_hosts, path)
        lspci(ssh_hosts, path)
        nvrm(ssh_hosts, path)
        pending(ssh_hosts, path)
        remapping(ssh_hosts, path)
        print("The results are at location: " + path)

