# Technical background

## Serverless Part

This implementation uses [Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Concepts/functionsoverview.htm) and [Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm) to communicate the status of the nodes to a [Queue](https://docs.oracle.com/en-us/iaas/Content/queue/overview.htm). The creation of the function requires an [Auth Token](https://docs.oracle.com/en-us/iaas/Content/Registry/Tasks/registrygettingauthtoken.htm) to authenticate to the [Oracle Registry](https://docs.oracle.com/en-us/iaas/Content/Registry/Concepts/registryoverview.htm) where the function image is stored. Auth Tokens are limited and an existing one can be specified during the configuration.

> [!WARNING]
> By default, a user is limited are limited to 2 Auth Tokens. It is recommended to use an existing Auth Token that can be created in your home region prior to the stack deployment. In case you do not select *"Use existing auth token"*, a Auth Token will be created.
> Please note that after the creation, some time (up to 5 minutes) is needed for the Auth Token to be valid to authenticate with `docker login`. This is why a `time_sleep` resource is executed in Terraform.

## Workflow

![Workflow for node configuration](/images/workflow.png)

### Serverless function

When nodes are added or removed, an Event triggers an OCI Function. This serverless function will register nodes in the DNS and change their OCI display name to the slurm name if `Change hostname` is set to `true` in the configuration. The current approach is using the Oracle DNS service instead of the `/etc/hosts` file.

When a node is created:
  * Sends a message to the Queue with the IP of the node and status `Starting`
  * Adds DNS entry (hostname_convention must be a tag)
  * Changes the OCI display name to the slurm name (if option checked)

When a node is deleted:
  * Sends a message to the Queue with the IP of the node and status `Terminating`
  * Removes DNS entry 

### Node configuration

Each compute node will run an Ansible script locally. The nodes will be tagged with the name of the controller node they belong to. That node will mount a network filesystem `/config` folder to store the Ansible playbooks and the keys. The Ansible playbook will run all the tasks that can be run on the host including a task that creates a HTTP server boradcasting node information on port 9876.

Example of the information:
```
ip_address: '172.16.0.66',
AD: 'xXXX:CA-TORONTO-1-AD-1',
cluster_name: 'loving-flounder',
compartment: 'ocid1.compartment.oc1..xxxxxxxxxxxxxxxxx',
controller_name: 'loving-flounder-controller',
fss_mount: 'None',
hostname: 'loving-flounder-controller',
hpc_island: 'None',
networkBlockId: 'None',
oci_name: 'loving-flounder-controller',
ocid: 'ocid1.instance.oc1.ca-toronto-1.xxxxxxxxxxxxxxxxxxxxxxxx',
rackID: 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
railId: 'None',
role: 'controller',
serial: 'Not Specified',
shape: 'VM.Standard.E4.Flex',
status: 'configured',
```

### Controller service and actions for configuration

The controller node:
* runs a service that reads messages in the Queue and stores the information in the MySQL database,
* queries informations of sent by the webservers on each of the compute nodes and store these in the MySQL database,
* runs Ansible roles locally when the nodes are marked as `Ready` in order to finalise the cluster setup:
  * Runs the `Fix_ldap` role
  * Adds/removes the node to `prometheus.yml`
  * Adds/removes the node in the slurm configuration, i.e. `topology.conf` and `gres.conf`