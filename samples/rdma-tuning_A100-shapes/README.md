# A100 RDMA and PCIe tuning samples

These scripts inspect or change PCIe maximum-read-request and Mellanox NIC settings for `BM.GPU.B4.8`, `BM.GPU.A100-v2.8`, and `BM.GPU4.8` shapes.

- `check_pcie_max_read.sh` reads the current PCIe maximum read setting.
- `pcie_max_read.sh` sets the PCIe maximum read request size to 4096 bytes.
- `pcie_max_read_default.sh` sets it to 512 bytes.
- `rdma-nic-tuning-1.sh` enables advanced PCI settings and resets NIC firmware.
- `rdma-nic-tuning-2.sh` sets `MAX_ACC_OUT_READ`.
- `rdma-nic-tuning-validate.sh` reads the resulting NIC settings.

Run these scripts as a privileged user and only after confirming the target shape. Several commands change device or firmware settings and may require a reset. Test them on a non-production node first and use a maintenance window for any wider rollout.
