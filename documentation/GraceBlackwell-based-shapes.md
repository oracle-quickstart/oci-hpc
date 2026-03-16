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
mgmt clusters create --count 16 --cluster my_cluster --instancetype default --fabric ocid1.computegpumemoryfabric.oc1..... 
```

This creates a `computecluster` with the name my_cluster as well as a `computegpumemorycluster` with a name `cluster_xxxxx`.  When a `computegpumemorycluster` is created OCI automatically spins up the number of instances given in `--count`.  This is reflected in the `mgmt fabrics list` command output after a few minutes. The nodes and their respective informations can be seen with:
```
mgmt nodes list
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ hostname                 ┃ healthcheck_recommendat… ┃ status  ┃ compute_status ┃ cluster_name  ┃ memory_cluster_name ┃ ocid                      ┃ serial        ┃ ip_address    ┃ shape               ┃
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
To add more nodes from a `computegpumemoryfabric` that is already included in this cluster, use the corresponding `cluster_xxxxx` name for these nodes as shown as `memory_cluster_name` in `mgmt fabrics list`:
```
mgmt clusters add node --count 2 --memorycluster cluster_xxxxx
```
To delete a `computegpumemorycluster` and terminate all of the instances:
```
mgmt clusters delete --memory_cluster cluster_xxxxx