
# OCI Meshpinger

Meshpinger is a tool for validating network layer connectivity between RDMA NICs on a
cluster network in OCI. The tool initiates an ICMP ping from every RDMA NIC
port on the cluster network to every other RDMA NIC port on the same cluster network and
reports back the success/failure status of the pings performed in the form of logs

Running the tool before starting workload on a cluster network should serve as a good precheck
step to gain confidence on the network reachability between RDMA NICs. Typical causes for
reachability failures that the tool can help pinpoint are,

1. Host rdma interface down

2. Host rdma interface missing IP configuration

3. Host rdma interface missing mac

4. Host rdma interface enumeration issues

5. Network connectivity issues between <src,dst> pair of IPs

# Running Meshpinger

Meshpinger is installed on the controller host of the hpc cluster. Once user is logged into the controller host, they can trigger meshpinger using the following options,

- If controller host is supporting only one cluster, run meshpinger on all hosts in that cluster. The cluster is auto-detected in this option.
```
/opt/oci-hpc/healthchecks/run_meshpinger.sh
```

- If controller host is supporting more than 1 cluster, run meshpinger on all hosts in a cluster explicitly specified by its clustername
```
/opt/oci-hpc/healthchecks/run_meshpinger.sh --hpcclustername <hpcclustername>
```

Run meshpinger on a list of hosts specified in a file. A host can be specified by its IP address or hostname. It is expected that the host will be SSH-able from the controller host
```
/opt/oci-hpc/healthchecks/run_meshpinger.sh --hostlisttfile <filename>
```

# Output

- All rdma interface configuration issues are reported like the sample below,

```
Faulty RDMA interfaces(Link down/misconfigured)

    Hostid/Serial/hostname      Interface    RDMA_IP    PCI           MAC                Link Status
--  --------------------------  -----------  ---------  ------------  -----------------  -------------
 0  GPU-711/2109XCL016/GPU-711  rdma1        0.0.0.0    0000:98:00.1  b8:ce:f6:00:12:29  DOWN
 1  GPU-278/2110XCL04V/GPU-278  rdma1        0.0.0.0    0000:98:00.1  04:3f:72:e0:6b:0d  DOWN
```

- If there are ping failures from the run, total number of unique <srcInterface,dstInterface> pings that failed per host is printed as a table like the sample below,

```
ICMP ping failures per host

    Hostid/Serial/Hostname        Total Failures
--  --------------------------  ----------------
 0  GPU-711/2109XCL016/GPU-711                 1
 1  GPU-278/2110XCL04V/GPU-278                 1
```
Logfile of the current run that enumerates all <srcInterface,dstInterface> combinations that failed ping is printed like,

```
<src,dst> interfaces that failed ping are listed at end of the log file meshpinger_log_20241008220615_ocid1.tenancy.oc1..aaaaaaaabddc4obuhgvifcrh6esmw6554ityaqrvxulcksl255gbwehtcq.txt
```


- If there are no ping failures from the run, following message is printed

```
All pings succeeded!!
```
- Cluster information that includes rdma interface details gathered from the run is stored in a file cluster_info.txt in the current directory, same is printed as below,
```
clusterinfo file - cluster_info.txt
```

# Options
Other options supported are shown in the help text below.

```
/opt/oci-hpc/healthchecks/run_meshpinger.sh --help

usage: ./run_meshpinger.sh [-h]
                            [--hostlistfile HOSTLISTFILE | --hpcclustername HPCCLUSTERNAME]
                            [--clusterinfo CLUSTERINFO] [--ssh_port SSH_PORT]
                            [--ping_timeout PING_TIMEOUT]
                            [--dump_arp_on_failure] [--flush_arp]
                            [--nic_model NIC_MODEL]
                            [--objectstoreurl OBJECTSTOREURL] [--enable_inter_rail_ping]
                            [--threads_per_intf THREADS_PER_INTF] [--verbose]

optional arguments:
  -h, --help            show this help message and exit
  --hostlistfile HOSTLISTFILE
                        File listing name/ip of the hosts to include in
                        meshping
  --hpcclustername HPCCLUSTERNAME
                        OCI HPC stack clustername
  --clusterinfo CLUSTERINFO
                        Use this cluster info file (generated from previous
                        runs) and skip gathering cluster information in this
                        run
  --ssh_port SSH_PORT   ssh port to use, port 22 will be used if not specified
  --ping_timeout PING_TIMEOUT
                        Duration ping waits for reply before timing out,
                        default is 1sec
  --dump_arp_on_failure
                        Log arp entry for failed pings
  --flush_arp           Flush arp cache before starting pinger
  --nic_model NIC_MODEL
                        Model of the RDMA NIC eg. MT2910(CX-7) to use if auto
                        detect fails
  --objectstoreurl OBJECTSTOREURL
                        ObjectStore PAR URL where mesh pinger logs will be
                        uploaded
  --enable_inter_rail_ping
                        Include this argument to perform pings across the rails.
                        If so pinger will do a full mesh ping
  --threads_per_intf THREADS_PER_INTF
                        parallel ping threads per local rdma interface,
                        default is 16
  --verbose             Log all debug messages including successful pings.
                        Default is to log only failed pings
```

# Description
Detailed description of each option is below,

**--hostlistfile**

Path to file containing the list of hosts to be used for current meshpinger run. A host can be specified by its IP address or its hostname but it should be SSH-able via either of these 2 strings specified. String specified here is listed as Hostid on the final report of meshping run

**--hpcclustername**

Clustername specified when the cluster was created using OCI HPC stack


**--clusterinfo**

File containing cluster information generated from a previous meshpinger run. When this is specified, current run will skip gathering RDMA interface details from the hosts and move on to doing actual meshping tests saving some runtime. Note that specifying this option forces meshpinger to use RDMA interface details collected previously which could be stale especially for attributes like link state, IP assignment

**--ssh_port**

Port to use for ssh to hosts specified in the hostlistfile. By default port 22 will be used if this is not specified

**--ping_timeout**

Time in milliseconds that ping waits for a successful reply from remote IP including the time it takes for arp resolution. This timeout is 1 second by default if this option is not specified and overall meshpinger performs 10 retries for each of the remote IPs before marking it as a ping failure

**--dump_arp_on_failure**

When this option is specified, for each of the ping failures the corresponding arp table entry(including the status field) for the remote IP on the local host will be dumped in meshpinger logs. By default this is disabled

**--flush_arp**

When this option is specified, meshpinger will flush the arp table on each of the hosts before starting the ping validation test

**--nic_model**

NIC model to use (e.g MT2910 for CX-7) for filtering out RDMA interfaces from front-end network interfaces while gathering RDMA interface information on each host. By default, meshpinger determines the model based on the model of majority of interfaces on the host given that backend network interface count always exceeds frontend network interface count.

**--objectstoreurl**

Pre-Authenticated Request(PAR) url where meshpinger logs will be uploaded. This can be used by customers to easily share meshpinger logs with OCI during any incidents. OCI can provide a PAR to objectstore bucket and share it with customer to enable sharing of meshpinger logs.

**--enable_inter_rail_ping**

This option specifies all rdma interfaces on hosts in the hostlist file are part of a single subnet. In this case meshpinger will do pings to all remote IPs from all local interfaces on a given host. It is to be noted that when this option is chosen net.ipv4.neigh.default.gc_threshX [X=1-3] sysctl setting on every host may need to be bumped up to hold the necessary arp entries per local interface. Eg. For running meshpinger on a 512 host cluster with each host having 16 rdma interface, size of the arp table should be atleast 130816(511 * 16 * 16). Accordingly it is recommended to set all the 3 sysctl thresholds -  net.ipv4.neigh.default.gc_threshX[X=1-3] to 130816. By default, meshpinger only pings along the rails.

**--threads_per_intf**

By default meshpinger running on each of the hosts in the hostlist file uses 16 parallel threads per local interface to perform parallel pings. This option overrides that setting with allowed values of 1-32

**--verbose**

By default only ping failures are logged to limit the log file size. When this option is specified succeeding pings are also logged


