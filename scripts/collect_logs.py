import os
from datetime import datetime
import argparse
import shlex
import subprocess
import sys
import requests

def getDateTime():
    # datetime object containing current date and time
    now = datetime.now()
    dt_string = now.strftime("%m%d%Y%H%M%S")
    return dt_string


# create directory to hold results
def createDir(hostname):
    # Parent Directory path
    username = os.getlogin()
    parent_dir = "/home/" + username + "/"
    # directory name
    directory = str(hostname) + "_" + getDateTime()
    # Path
    path = os.path.join(parent_dir, directory)
    try:
        os.mkdir(path)
    except OSError as error:
        print(error)
        sys.exit(-1)
    return path


def run_cmd(cmd=None):
    """ Run command on shell"""
    cmd_split = shlex.split(cmd)
    try:
        results = subprocess.run(cmd_split, shell=False, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=True, encoding='utf8')
        output = results.stdout.splitlines()
    except subprocess.CalledProcessError as e_process_error:
        return (9000, f"Error code: {e_process_error.returncode} Output: {e_process_error.output}")
    return output


# run nvidia bug report
def nvidiaBugReport(host, path):
    cmd = f'ssh {host} "cd {path}; sudo /usr/bin/nvidia-bug-report.sh"'
    raw_result = run_cmd(cmd)
    if isinstance(raw_result, tuple):
        if raw_result[0] == 9000:
            print("Error in running nvidia bug report script for " + host)
            print(raw_result[1])
            return False
    else:
        username = os.getlogin()
        cmd = f'mv /home/{username}/nvidia-bug-report.log.gz {path}'
        run_cmd(cmd)
        changeOwner(path)
        return True


# run sosreport
def sosReport(host, path):
    os_version = getOS(host)
    if os_version == "Oracle":
        cmd = f'ssh {host} "sudo sosreport --batch -q -k rpm.rpmva=off --tmp-dir /tmp/"'
    elif os_version == "Ubuntu":
        cmd = f'ssh {host} "sudo sos report --batch -q -k rpm.rpmva=off --tmp-dir /tmp/"'
    else:
        print("Error in running sosreport for " + host)
        return False
    raw_result = run_cmd(cmd)
    if isinstance(raw_result, tuple):
        if raw_result[0] == 9000:
            print("Error in running sosreport for " + host)
            print(raw_result[1])
            return False
    else:
        filename = [match for match in raw_result if ".tar.xz" in match]
        sosfile = filename[0].strip()
        sosrepfile = sosfile.rsplit('/', 1)[1]
        cmd = f'ssh {host} "sudo mv /tmp/{sosrepfile} {path}"'
        run_cmd(cmd)
        changeOwner(path)
        sosrepfile_sha256 = sosrepfile + ".sha256"
        cmd = f'ssh {host} "sudo mv /tmp/{sosrepfile_sha256} {path}"'
        run_cmd(cmd)
        changeOwner(path)
        return True


# get console history logs
def consoleHistoryLogs(host, path, compartment):
    if compartment is None:
        res = requests.get('http://169.254.169.254/opc/v1/instance')
        compartment_id = res.json()['compartmentId']
    else:
        compartment_id = compartment
    out = subprocess.Popen(["cat /etc/hosts | grep "+host+" | awk '{print $4}'"],stdout=subprocess.PIPE, stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
    stdout,stderr = out.communicate()
    name = stdout.split()
    instance_display_name = name[0]
    cmd = f'oci compute instance list --compartment-id {compartment_id} --display-name {instance_display_name} --auth instance_principal --query data[0].id'
    instance_id = run_cmd(cmd)
    if isinstance(instance_id, tuple):
        if instance_id[0] == 9000:
            print("Error in getting instance OCID." + instance_id[1])
            return False
    instance_id_str = instance_id[0]
    cmd = f'oci compute console-history capture --instance-id {instance_id_str} --auth instance_principal --query data.id'
    instance_console_history = run_cmd(cmd)
    if isinstance(instance_console_history, tuple):
        if instance_console_history[0] == 9000:
            print("Error in getting instance OCID." + instance_console_history[1])
            return False
    instance_console_history_str = instance_console_history[0]
    filename = "/" + host + "_" + "console_history"
    full_path = path + filename
    cmd = f'oci compute console-history get-content --file {full_path} --instance-console-history-id {instance_console_history_str} --length 100000 --auth instance_principal'
    raw_result = run_cmd(cmd)
    if isinstance(raw_result, tuple):
        if raw_result[0] == 9000:
            print("Error in getting console history log for " + host)
            print(raw_result[1])
        return False
    else:
        return True


# change ownership of all files to user so that the files can be copied
def changeOwner(path):
    username = os.getlogin()
    cmd = f'sudo chown -R {username}:{username} {path}'
    run_cmd(cmd)


def isNodeSshable(host):
    cmd = f'ssh -o ConnectTimeout=10 {host} "cat /etc/os-release | grep PRETTY_NAME"'
    raw_result = run_cmd(cmd)
    if isinstance(raw_result, tuple):
        if raw_result[0] == 9000:
            return False
    elif 'PRETTY_NAME' in raw_result[0]:
        return True
    else:
        return False

def getOS(host):
    cmd = f'ssh -o ConnectTimeout=10 {host} "cat /etc/os-release | grep PRETTY_NAME"'
    raw_result = run_cmd(cmd)
    if isinstance(raw_result, tuple):
        print("Error in determining OS")
        if raw_result[0] == 9000:
            return "error"
    elif 'Oracle' in raw_result[0]:
        return "Oracle"
    elif 'Ubuntu' in raw_result[0]:
        return "Ubuntu"
    else:
        return "error"
    

parser = argparse.ArgumentParser(description = 'Get nvidia bug report, sosreport, console history logs for a particular host if it is reachable. If it is not reachable, then console history logs are generated.')
parser.add_argument('--hostname', help = "Provide a hostname", required = True)
parser.add_argument('--compartment-id', help = "Provide the compartment OCID where the given host is")
args = parser.parse_args()
hostname = args.hostname
compartment = args.compartment_id
if hostname is None:
    sys.exit(-1)
else:
    path = createDir(hostname)
    changeOwner(path)
    node_reachable = isNodeSshable(hostname)
    if node_reachable:
        bug_report = False
        sos_report = False
        console_logs = False
        if nvidiaBugReport(hostname, path):
            bug_report = True
        if sosReport(hostname, path):
            sos_report = True
        if consoleHistoryLogs(hostname, path, compartment):
            console_logs = True
        if bug_report and sos_report and console_logs:
            print("The nvidia bug report, sosreport, and console history logs for " + hostname + " are at " + path)
        elif bug_report and not sos_report and not console_logs:
            print("The nvidia bug report for " + hostname + " is at " + path)
        elif bug_report and sos_report and not console_logs:
            print("The nvidia bug report and sosreport for " + hostname + " are at " + path)
        elif bug_report and not sos_report and console_logs:
            print("The nvidia bug report and console history logs for " + hostname + " are at " + path)
        elif not bug_report and sos_report and not console_logs:
            print("The sosreport for " + hostname + " is at " + path)
        elif not bug_report and not sos_report and console_logs:
            print("The console history logs for " + hostname + " is at " + path)
        elif not bug_report and sos_report and console_logs:
            print("The sosreport and console history logs for " + hostname + " are at " + path)
        else:
            sys.exit(-1)
    else:
        if consoleHistoryLogs(hostname, path, compartment):
            print(hostname + " is not reachable. The console history logs are at " + path)
