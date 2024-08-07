#!/bin/bash
date
eval "$(ssh-agent -s)" >/dev/null ; ssh-add ~/.ssh/id_rsa >/dev/null
cat /etc/hosts | grep .local.vcn | awk '{print $2}' > /tmp/all_hosts

/opt/oci-hpc/healthchecks/meshpinger_bm/run_meshpinger --hostlistfile /tmp/all_hosts --singlesubnet --ping_timeout 100 2>&1 | grep "INCOM\|DELAY" | awk '{print $6}' | sort -u | tee failed_nodes