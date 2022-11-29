Problem:
When node running NFS needs to be terminated due to H/W failure, site.yml playbook fails, sudo umount /nfs/scratch hangs. 

Solution:
1. Manually change the ansible inventory file (/etc/ansible/hosts) on bastion. You will need to use sudo.
    a. To replace the [nfs] group hostname with another node of the cluster to act as NFS server.
    Example: <instance name> ansible_user=opc role=nfs
    b. If the node that was deleted is still there in [compute_configured] group, then remove it.
2. Run the script fix_nfs.sh.

