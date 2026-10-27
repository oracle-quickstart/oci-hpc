# Cluster management scripts

`create_instance_config.py` interactively copies an OCI instance configuration, optionally replacing its SSH key, boot-volume size, image, cloud-init data, or display name. It can then attach the new configuration to instance pools in a Cluster Network or to a GPU Memory Cluster.

Run it from an OCI compute instance that can use instance-principal authentication and has the OCI Python SDK installed:

```bash
python3 create_instance_config.py --compartment-id <compartment_ocid>
```

This script creates OCI resources and updates existing cluster capacity definitions. Confirm the selected instance configuration and update mode before accepting each interactive prompt.
