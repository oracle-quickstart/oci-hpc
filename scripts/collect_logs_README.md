This is a script to collect nvidia bug report, sosreport, console history logs.
 
The script needs to be run from the bastion. In the case where the host is not ssh-able, it will get only  console history logs for the same.
 
It requires the below argument.
--hostname <HOSTNAME>
 
And --compartment-id <COMPARTMENT_ID> is optional (i.e. assumption is the host is in the same compartment as the bastion). 
 
Where HOSTNAME is the node name for which you need the above logs and COMPARTMENT_ID is the OCID of the compartment where the node is.

The script will get all the above logs and put them in a folder specific to each node in /home/{user}. It will give the folder name as the output.

Assumption: For getting the console history logs, the script expects to have the node name in /etc/hosts file.

Examples:

python3 collect_logs.py --hostname compute-permanent-node-467
The nvidia bug report, sosreport, and console history logs for compute-permanent-node-467 are at /home/ubuntu/compute-permanent-node-467_06132023191024
 
python3 collect_logs.py --hostname inst-jxwf6-keen-drake
The nvidia bug report, sosreport, and console history logs for inst-jxwf6-keen-drake are at /home/ubuntu/inst-jxwf6-keen-drake_11112022001138
 
for x in `less /home/opc/hostlist` ; do echo $x ; python3 collect_logs.py --hostname $x; done ;
compute-permanent-node-467
The nvidia bug report, sosreport, and console history logs for compute-permanent-node-467 are at /home/ubuntu/compute-permanent-node-467_11112022011318
compute-permanent-node-787
The nvidia bug report, sosreport, and console history logs for compute-permanent-node-787 are at /home/ubuntu/compute-permanent-node-787_11112022011835
 
Where hostlist had the below contents
compute-permanent-node-467
compute-permanent-node-787