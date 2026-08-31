# Notes on Deployments for Memory Fabric Based Shapes, such as Nvidia GB200 / GB300

When deploying these shapes your initial cluster scale up actions once you connect to the cluster will differ depending on whether or not you choose to add execution hosts during the stack apply or not.  

On the controller host you can view the available GPU Memory Fabrics like this:
```
mgmt fabrics list
                                                                        Fabrics
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┓
┃ id                                                                           ┃ lifecycle_state ┃ fabric_health ┃ memory_cluster ┃ OCCUPIED ┃ AVAILABLE ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━┩
│ ocid1.computegpumemoryfabric.oc1....                                         │ AVAILABLE       │ HEALTHY       │ None           │ 0        │ 18        │
└──────────────────────────────────────────────────────────────────────────────┴─────────────────┴───────────────┴────────────────┴──────────┴───────────┘
```

NOTE:  If your stack apply included an initial GPU Memory Fabric to launch on, skip down to the `mgmt clusters add memory-fabric` command below.  
If you did NOT add any compute hosts via GPUMemoryFabrics during the initial stack deployment/apply, you can create the initial Compute Cluster that is required for inter-rack communication AND GPU Memory Cluster like this:

1. Check that the `lifecycle_state` is `AVAILABLE`, the `fabric_health` must be `HEALTHY`, and check `AVAILABLE` nodes:

2. Use the OCID from above for `--fabric`, as well as the number of `AVAILABLE` hosts for `--count`:

```
mgmt clusters create --count 16 --cluster my_cluster --instancetype default --fabric ocid1.computegpumemoryfabric.oc1..... --targetsize 18
```

To create the initial Compute Cluster and consume every unused GPU Memory Fabric that has `AVAILABLE` hosts:
```
mgmt clusters create --cluster my_cluster --instancetype default --all --targetsize 18
```

To consume every unused GPU Memory Fabric that has at least 12 `AVAILABLE` hosts:
```
mgmt clusters create --cluster my_cluster --instancetype default --all --minimum-gmc-size 12 --targetsize 18
```

To create the initial Compute Cluster and consume every unused GPU Memory Fabric in a specific Compute Local Block, Compute Network Block, or Compute HPC Island:
```
mgmt clusters create --cluster my_cluster --instancetype default --compute-local-block-id ocid1.computelocalblock.oc1..... --targetsize 18
mgmt clusters create --cluster my_cluster --instancetype default --compute-network-block-id ocid1.computenetworkblock.oc1..... --targetsize 18
mgmt clusters create --cluster my_cluster --instancetype default --compute-hpc-island-id ocid1.hpcisland.oc1..... --targetsize 18
```

To create the initial Compute Cluster with a selected list of GPU Memory Fabrics:
```
mgmt clusters create --count 18 --cluster my_cluster --instancetype default --fabric ocid1.computegpumemoryfabric.oc1.....,ocid1.computegpumemoryfabric.oc1..... --targetsize 18
```

This creates a `computecluster` with the name my_cluster as well as a `computegpumemorycluster` with a name `cluster_xxxxx`.  When a `computegpumemorycluster` is created OCI automatically spins up the number of instances given in `--count`.  Use `--targetsize` when you want OCI's memory cluster scale config to target a larger size than the initial node count. This is reflected in the `mgmt fabrics list` command output after a few minutes. The nodes and their respective informations can be seen with:
```
mgmt nodes list
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ hostname                 ┃ healthcheck_recommendat… ┃ status  ┃ compute_status ┃ cluster_name  ┃ memory_cluster_id ┃ ocid                      ┃ serial        ┃ ip_address    ┃ shape               ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ trusting-dory-controller │                          │ running │ configuring    │ cluster-name  │ None                │ ocid1.instance.oc1.ap-sy… │ Not Specified │ 172.16.xxx.xxx│ VM.Standard.E5.Flex │
│ GPU-123                  │ Healthy                  │ running │ configuring    │ cluster-name  │ cluster-name_wuuja  │ ocid1.instance.oc1.ap-sy… │ 1234ABCXXX    │ 172.16.xxx.xxx│ BM.GPU.GB200.4      │
│ GPU-456                  │ Healthy                  │ running │ configuring    │ cluster-name  │ cluster-name_wuuja  │ ocid1.instance.oc1.ap-sy… │ 5678DEFYYY    │ 172.16.xxx.xxx│ BM.GPU.GB200.4      │
└──────────────────────────┴──────────────────────────┴─────────┴────────────────┴───────────────┴─────────────────────┴───────────────────────────┴───────────────┴───────────────┴─────────────────────┘
```

> [!WARNING]
> Use the above command `mgmt clusters create ...` **ONLY** to add the first set of instances (see below how to add `gpumemoryfabrics` to the compute cluster named `gb200` that has been created above), otherwise inter-rack communication will not work.

To add nodes from additional `computegpumemoryfabrics` to an existing compute cluster:
```
mgmt clusters add memory-fabric --count 18 --cluster gb200 --instancetype default --fabric ocid1.computegpumemoryfabric.oc1.... 
```
To add all unused GPU Memory Fabrics that have `AVAILABLE` hosts:
```
mgmt clusters add memory-fabric --all --cluster gb200 --instancetype default
```
To add all unused GPU Memory Fabrics that have at least 12 `AVAILABLE` hosts:
```
mgmt clusters add memory-fabric --all --cluster gb200 --instancetype default --minimum-gmc-size 12
```
To add all unused GPU Memory Fabrics in a specific Compute Local Block, Compute Network Block, or Compute HPC Island:
```
mgmt clusters add memory-fabric --cluster gb200 --instancetype default --compute-local-block-id ocid1.computelocalblock.oc1.....
mgmt clusters add memory-fabric --cluster gb200 --instancetype default --compute-network-block-id ocid1.computenetworkblock.oc1.....
mgmt clusters add memory-fabric --cluster gb200 --instancetype default --compute-hpc-island-id ocid1.hpcisland.oc1.....
```
To add a selected list of GPU Memory Fabrics:
```
mgmt clusters add memory-fabric --count 18 --cluster gb200 --instancetype default --fabric ocid1.computegpumemoryfabric.oc1....,ocid1.computegpumemoryfabric.oc1....
```
To add more nodes from a `computegpumemoryfabric` that is already included in this cluster, use the corresponding `cluster_xxxxx` name for these nodes as shown as `memory_cluster_id` in `mgmt fabrics list`:
```
mgmt clusters add node --count 2 --memorycluster cluster_xxxxx
```
To delete a `computegpumemorycluster` and terminate all of the instances:
```
mgmt clusters delete --memory_cluster cluster_xxxxx
mgmt clusters delete --memory_cluster cluster_xxxxx --force-skip-recycle
mgmt clusters delete --memory_cluster cluster_xxxxx --force-full-recycle
```