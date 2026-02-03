# tfvars for deployment without fss

region="eu-paris-1"

ad="jLaG:EU-PARIS-1-AD-1"

controller_ad="jLaG:EU-PARIS-1-AD-1"

login_ad="jLaG:EU-PARIS-1-AD-1"

monitoring_ad="jLaG:EU-PARIS-1-AD-1"

controller_boot_volume_size=1024

controller_boot_volume_backup=true

controller_shape="VM.Standard.E4.Flex"

rdma_enabled="false"

instance_pool_shape="VM.Standard.E4.Flex"

node_count=2

boot_volume_size=256

use_marketplace_image=false

slurm=true

slurm_version="25.11.0-1"

login_node=true

login_shape="VM.Standard.E4.Flex"

login_boot_volume_size=256

monitoring_node=true

monitoring_shape="VM.Standard.E4.Flex"

monitoring_boot_volume_size=256

controller_ocpus=2

instance_pool_ocpus=2

login_ocpus=2

monitoring_ocpus=4

enroot=true
cluster_monitoring=true
alerting=true
pyxis=true
pam=true

unsupported=true
unsupported_controller=true
use_marketplace_image_controller=false


change_hostname=true
hostname_convention="GPU"
