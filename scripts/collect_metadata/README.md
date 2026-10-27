# Metadata collection

`collect_metadata.py` connects to one host or a file of hosts over SSH, reads OCI instance, host, and VNIC metadata, and writes selected fields as CSV to standard output or to a file.

Install the Python dependency listed in `requirements.txt`, then run one of the following commands:

```bash
python3 collect_metadata.py <host_or_ip>
python3 collect_metadata.py <hostfile> --csv metadata.csv
```

The script uses the selected user's key at `~/.ssh/id_ed25519` and expects SSH access to each target. The output fields are display name, hostname, private IP, network block, rack ID, availability domain, and instance ID.
