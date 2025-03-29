import oci

class ocicore:
    def __init__(self, user_logging):
        if user_logging:
            self.config_oci = oci.config.from_file()
            self.computeClient = oci.core.ComputeClient(self.config_oci)
            self.ComputeClientCompositeOperations = oci.core.ComputeClientCompositeOperations(self.computeClient)
            self.computeManagementClient = oci.core.ComputeManagementClient(self.config_oci)
            self.ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(self.computeManagementClient)
            self.virtualNetworkClient = oci.core.VirtualNetworkClient(self.config_oci)
            self.dns_client = oci.dns.DnsClient(self.config_oci)
        else:
            self.signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            self.computeClient = oci.core.ComputeClient(config={}, signer=self.signer)
            self.ComputeClientCompositeOperations= oci.core.ComputeClientCompositeOperations(self.computeClient)
            self.computeManagementClient = oci.core.ComputeManagementClient(config={}, signer=self.signer)
            self.ComputeManagementClientCompositeOperations = oci.core.ComputeManagementClientCompositeOperations(self.computeManagementClient)
            self.virtualNetworkClient = oci.core.VirtualNetworkClient(config={}, signer=self.signer)
            self.dns_client = oci.dns.DnsClient(config={}, signer=self.signer)

class ocicluster:
    def __init__(self, comp_ocid, cn_ocid, CN, cluster_name, username, inventory, hostfile,  \
                 playbooks_dir, slurm_name_change, hostname_convention, autoscaling):
        self.comp_ocid = comp_ocid
        self.cn_ocid = cn_ocid
        self.CN = CN
        self.cluster_name = cluster_name
        self.username = username
        self.inventory = inventory
        self.hostfile = hostfile
        self.playbooks_dir = playbooks_dir
        self.slurm_name_change = slurm_name_change
        self.hostname_convention = hostname_convention
        self.autoscaling = autoscaling