# tfvars for deployment without fss

current_user_ocid="ocid1.user.oc1..aaaaaaaakvxvxu4xxtwjtkxicqkmcr6u635yq33erb6vqr64mcdsayjxr2eq"

ssh_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCgt7oe8ZBg1ff2p4MVS578cLYcUnTZtEi52c98rfko0l44AfvuajV8dRPR/+80AvhcYGJLEnKXEVX9gsOB4qIaTEJkh9OeQYYHCKR+jDv5zQIZSE1vPIQKcxksoCzqGIlzhHMBgO9nRCpJEcTR/wIlgcbDIX+Z2nvScFjQP1oaex5doybi7ioXwIqCyuS3iBGMCqtxKdXeAgXHQ6Yzyp4a1izgk44oZMbEO7A8Jtuhl8yNn1MeJQNLaUP4yJdKGtbkIjopUAa24VmmcihNhmrlBNqeRY9kOKYJBPWvKY6sZvVBAn2KcqaptHxvuMYcH5NpQaGdsoXvZWbCKSSPfoFp ssh-key-2025-09-04"

region="eu-marseille-1"

tenancy_ocid= "ocid1.tenancy.oc1..aaaaaaaawxdcmyu3bxuemm3yfj7jojapxsm6dmyx6s344bn6zsqb2ebznoyq"

targetCompartment="ocid1.compartment.oc1..aaaaaaaajnic545smyjdep32cvlsiljscacjkrsqhl7xfdoqk5p64w6zhl2a"

vcn_compartment="ocid1.compartment.oc1..aaaaaaaajnic545smyjdep32cvlsiljscacjkrsqhl7xfdoqk5p64w6zhl2a" 

ad="jLaG:EU-MARSEILLE-1-AD-1"

controller_ad="jLaG:EU-MARSEILLE-1-AD-1"

login_ad="jLaG:EU-MARSEILLE-1-AD-1"

monitoring_ad="jLaG:EU-MARSEILLE-1-AD-1"

controller_boot_volume_size=1024

controller_boot_volume_backup=true

controller_shape="VM.Standard.E4.Flex"

rdma_enabled="false"

instance_pool_shape="VM.Standard.A1.Flex"

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
unsupported_login=true
unsupported_monitoring=true

use_marketplace_image_login=false
use_marketplace_image_monitoring=false

change_hostname=true
hostname_convention="GPU"
