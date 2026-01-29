"""
OCI Metadata Client Utilities

This module provides a unified interface for fetching metadata from various Oracle Cloud Infrastructure (OCI)
services. It implements a handler-based architecture where each OCI service namespace has a dedicated handler
that knows how to fetch resource information and map resource attributes to tags.

Architecture:
    The module uses three main components:

    1. OCIClientFactory: Factory class for creating OCI SDK clients with standardized configuration
       (config, signer, retry strategy). Ensures all clients are initialized consistently.

    2. ResourceHandler (ABC): Abstract base class defining the interface for service-specific handlers.
       Each handler must implement methods to:
       - Identify the resource ID key in metric tags
       - Initialize required OCI SDK clients
       - Retrieve client instances
       - Fetch resource metadata and return attribute mappings

    3. OCIMetaClient: Main entry point that routes requests to appropriate handlers based on namespace.
       Maintains a registry of handlers for different OCI services and coordinates resource metadata fetching.

Supported OCI Services:
    The module includes handlers for the following OCI services:
    - API Gateway (oci_apigateway)
    - Bastion (oci_bastion)
    - Block Storage (oci_blockstore)
    - Compute (oci_compute, oci_compute_infrastructure_health, oci_compute_instance_health, gpu_infrastructure_health, rdma_infrastructure_health)
    - Fast Connect (oci_fastconnect)
    - File Storage (oci_filestorage)
    - Internet Gateway (oci_internet_gateway)
    - Load Balancer (oci_lbaas)
    - Logging (oci_logging)
    - Lustre File System (oci_lustrefilesystem)
    - Management Agent (oci_managementagent)
    - NAT Gateway (oci_nat_gateway)
    - Object Storage (oci_objectstorage)
    - Container Engine for Kubernetes (oci_oke)
    - PostgreSQL Database (oci_postgresql)
    - Vault/Secrets (oci_secrets)
    - Service Connector Hub (oci_service_connector_hub)
    - Service Gateway (oci_service_gateway)
    - Virtual Cloud Network (oci_vcn, oci_vcnip)

Usage Example:
    >>> from oci_metrics_telegraf_utils import OCIMetaClient
    >>> from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
    >>>
    >>> # Initialize client with instance principal authentication
    >>> signer = InstancePrincipalsSecurityTokenSigner()
    >>> client = OCIMetaClient(config={}, signer=signer)
    >>>
    >>> # Fetch compute instance metadata
    >>> namespace = "oci_compute"
    >>> tags = {"resourceId": "ocid1.instance.oc1.phx.example"}
    >>> response, attr_mapping = client.get_resource(namespace, tags)
    >>>
    >>> # Extract display name from response
    >>> display_name = response.data.display_name
    >>> print(f"Instance name: {display_name}")

Extending the Module:
    To add support for a new OCI service:

    1. Create a handler class inheriting from ResourceHandler
    2. Implement all abstract methods (get_resource_identifier_key, initialize_clients, get_client, get_resource)
    3. Register the handler with OCIMetaClient using add_handler()
    4. Document the namespace and supported resource types

Attribute Mappings:
    Each handler returns an attribute mapping dict that specifies which resource attributes
    to extract as tags. For example: {"display_name": "display_name", "size_in_gbs": "size"}
    - Keys are the attribute names on the OCI resource object
    - Values are the tag names to use in the output metric

Thread Safety:
    Handlers use lazy initialization for OCI clients and are thread-safe after initialization.
    The OCIMetaClient itself is not thread-safe for handler registration but is safe for
    concurrent resource queries after initialization.
"""

from abc import ABC, abstractmethod
import logging
from typing import Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from oci.base_client import BaseClient

logger = logging.getLogger(__name__)


class OCIClientFactory:
    """
    Factory for creating OCI SDK clients with standardized configuration.

    This factory ensures all OCI clients are initialized with consistent
    authentication (config/signer), retry strategy, and other settings.
    Uses lazy client creation - clients are only instantiated when first requested.

    Attributes:
        config (dict): OCI configuration dictionary (empty for instance principals)
        signer: OCI authentication signer (config-based or instance principal)
        retry_strategy: OCI SDK retry strategy for handling API throttling and errors
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, signer: Optional[Any] = None, retry_strategy: Optional[Any] = None):
        """
        Initialize the OCI client factory.

        Args:
            config: OCI configuration dictionary (for config-based auth). Empty dict for instance principals.
            signer: OCI authentication signer (Signer instance or instance principal signer)
            retry_strategy: Custom retry strategy. If None, uses OCI SDK default retry strategy.
        """
        self.config = config or {}
        self.signer = signer

        if retry_strategy:
            self.retry_strategy = retry_strategy
        else:
            from oci.retry import DEFAULT_RETRY_STRATEGY
            self.retry_strategy = DEFAULT_RETRY_STRATEGY

    def create_client(self, client_class: type) -> Any:
        """
        Create an OCI SDK client with standardized configuration.

        Args:
            client_class: The OCI SDK client class to instantiate (e.g., ComputeClient, ObjectStorageClient)

        Returns:
            An initialized OCI SDK client instance with config, signer, and retry strategy

        Example:
            >>> factory = OCIClientFactory(config={}, signer=instance_principal_signer)
            >>> compute_client = factory.create_client(ComputeClient)
        """
        return client_class(
            config=self.config,
            signer=self.signer,
            retry_strategy=self.retry_strategy
        )


class ResourceHandler(ABC):
    """
    Abstract base class for handling specific OCI resource types.

    Each OCI service namespace has a dedicated ResourceHandler implementation
    that knows how to:
    1. Identify which tag contains the resource OCID
    2. Initialize the required OCI SDK clients
    3. Fetch resource metadata from the OCI API
    4. Map resource attributes to metric tags

    Handlers are registered with OCIMetaClient and invoked based on the
    metric namespace. This pattern allows extensible support for new
    OCI services without modifying the core client logic.

    Attributes:
        factory (OCIClientFactory): Factory for creating OCI SDK clients
        _clients (dict): Cache of initialized OCI clients (lazy initialization)

    Implementation Guide:
        To create a handler for a new OCI service:

        1. Inherit from ResourceHandler
        2. Implement get_resource_identifier_key() to return the tag key
           containing the resource OCID (usually "resourceId")
        3. Implement initialize_clients() to lazily create OCI SDK clients
        4. Implement get_client() to return requested client instances
        5. Implement get_resource() to:
           - Validate the resource_id is supported for this handler
           - Call the appropriate OCI SDK get_* method
           - Return (response, attribute_mapping) tuple
           - attribute_mapping maps resource attributes to tag names

    Example:
        >>> class MyServiceHandler(ResourceHandler):
        ...     def get_resource_identifier_key(self):
        ...         return "resourceId"
        ...
        ...     def initialize_clients(self):
        ...         if 'MyServiceClient' not in self._clients:
        ...             from oci.my_service import MyServiceClient
        ...             self._clients['MyServiceClient'] = self.factory.create_client(MyServiceClient)
        ...
        ...     def get_client(self, client_type):
        ...         if client_type not in self._clients:
        ...             self.initialize_clients()
        ...         return self._clients.get(client_type)
        ...
        ...     def get_resource(self, resource_id, tags):
        ...         self.initialize_clients()
        ...         response = self.get_client('MyServiceClient').get_resource(resource_id)
        ...         return response, {"display_name": "display_name"}
    """

    def __init__(self, factory: OCIClientFactory):
        """
        Initialize the resource handler.

        Args:
            factory: OCIClientFactory instance for creating OCI SDK clients
        """
        self.factory = factory
        self._clients: Dict[str, Any] = {}

    @abstractmethod
    def get_resource_identifier_key(self) -> str:
        """
        Return the tag key used to identify resource OCIDs for this handler.

        Most handlers return "resourceId", but some may use different keys
        (e.g., ServiceConnectorHubHandler uses "connectorId").

        Returns:
            The tag key name containing the resource OCID
        """
        pass

    @abstractmethod
    def initialize_clients(self) -> None:
        """
        Initialize required OCI SDK clients for this handler.

        Implementations should use lazy initialization - check if clients
        exist in self._clients before creating them. This method may be
        called multiple times.
        """
        pass

    @abstractmethod
    def get_client(self, client_type: str) -> Any:
        """
        Return the requested OCI SDK client for this handler.

        Args:
            client_type: String identifier for the client type (e.g., "ComputeClient")

        Returns:
            An initialized OCI SDK client instance

        Raises:
            ValueError: If the client_type is not supported by this handler
        """
        pass

    @abstractmethod
    def get_resource(self, resource_id: str, tags: Dict[str, Any]) -> Tuple[Any, Dict[str, str]]:
        """
        Retrieve resource metadata from OCI API and return attribute mapping.

        Args:
            resource_id: The OCID of the resource to fetch
            tags: Metric tags dictionary (may contain additional identifiers needed for the API call)

        Returns:
            A tuple of (response, attribute_mapping):
            - response: OCI SDK response object containing resource data
            - attribute_mapping: Dict mapping resource attributes to tag names
              Keys are attribute names on the resource object
              Values are tag names to use in output metrics

        Raises:
            ValueError: If the resource_id is not supported for this handler
        """
        pass


class APIGatewayHandler(ResourceHandler):
    """
    Handler for OCI API Gateway resources (oci_apigateway namespace).

    Handles API Gateway resources, fetching gateway details including
    display name and configuration.
    """

    def get_resource_identifier_key(self) -> str:
        return "resourceId"
    
    def initialize_clients(self):
        if 'GatewayClient' not in self._clients:
            from oci.apigateway import GatewayClient
            self._clients['GatewayClient'] = self.factory.create_client(GatewayClient)

    def get_client(self, client_type):
        if client_type == 'GatewayClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")
    
    def get_resource(self, resource_id, tags):
        if "apigateway" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the APIGatewayHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('GatewayClient').get_gateway(resource_id)
        return response, {"display_name": "display_name"}


class BastionHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'BastionClient' not in self._clients:
            from oci.bastion import BastionClient
            self._clients['BastionClient'] = self.factory.create_client(BastionClient)

    def get_client(self, client_type):
        if client_type == 'BastionClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "bastion" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the BastionHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('BastionClient').get_bastion(resource_id)
        return response, {"name": "display_name"}


class BlockStorageHandler(ResourceHandler):
    """
    Handler for OCI Block Storage service resources (oci_blockstore namespace).

    Handles both boot volumes and regular block volumes. Supports fetching
    volume details including size, availability domain, and display name.
    """

    def get_resource_identifier_key(self) -> str:
        return "resourceId"
    
    def initialize_clients(self):
        if 'BlockstorageClient' not in self._clients:
            from oci.core import BlockstorageClient
            self._clients['BlockstorageClient'] = self.factory.create_client(BlockstorageClient)

    def get_client(self, client_type):
        if client_type == 'BlockstorageClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):

        if "bootvolume" not in resource_id.split(".") and "volume" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the BlockStorageHandler: {resource_id}")
        
        self.initialize_clients()

        if "bootvolume" in resource_id.split("."):
            response = self.get_client('BlockstorageClient').get_boot_volume(resource_id)
            return response, {"display_name": "display_name", "size_in_gbs": "size", "availability_domain": "AD"}
        else:
            response = self.get_client('BlockstorageClient').get_volume(resource_id)
            return response, {"display_name": "display_name", "size_in_gbs": "size", "availability_domain": "AD"}    
        

class ComputeHandler(ResourceHandler):
    """
    Handler for OCI Compute service resources.

    Handles compute instances and is shared across multiple compute-related namespaces:
    - oci_compute: Standard compute instances
    - oci_compute_infrastructure_health: Infrastructure health metrics
    - oci_compute_instance_health: Instance health metrics
    - oci_computeagent: Compute agent metrics
    - gpu_infrastructure_health: GPU infrastructure health
    - rdma_infrastructure_health: RDMA infrastructure health

    All these namespaces ultimately reference compute instance resources.

    Attributes:
        NAMESPACES: Tuple of namespace strings that use this handler
    """

    NAMESPACES = ("oci_compute_infrastructure_health", "oci_compute_instance_health", "oci_computeagent", "oci_compute", "gpu_infrastructure_health", "rdma_infrastructure_health")

    def get_resource_identifier_key(self) -> str:
        return "resourceId"
    
    def initialize_clients(self):
        if 'ComputeClient' not in self._clients:
            from oci.core import ComputeClient
            self._clients['ComputeClient'] = self.factory.create_client(ComputeClient)

    def get_client(self, client_type):
        if client_type == 'ComputeClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "instance" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the ComputeHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('ComputeClient').get_instance(resource_id)
        return response, {"display_name": "display_name", "availability_domain": "AD"}


class FastConnectHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'VirtualNetworkClient' not in self._clients:
            from oci.core import VirtualNetworkClient
            self._clients['VirtualNetworkClient'] = self.factory.create_client(VirtualNetworkClient)

    def get_client(self, client_type):
        if client_type == 'VirtualNetworkClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):

        if "crossconnectgroup" not in resource_id.split(".") and "crossconnect" not in resource_id.split(".") and "virtualcircuit" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the FastConnectHandler: {resource_id}")
        
        self.initialize_clients()

        if "crossconnectgroup" in resource_id.split("."):
            response = self.get_client('VirtualNetworkClient').get_cross_connect_group(resource_id)
            return response, {"display_name": "display_name"}
        elif "crossconnect" in resource_id.split("."):
            response = self.get_client('VirtualNetworkClient').get_cross_connect(resource_id)
            return response, {"display_name": "display_name", "port_speed_shape_name": "port_speed_shape_name", "port_name": "port_name", "location_name": "location_name"}
        else:
            response = self.get_client('VirtualNetworkClient').get_virtual_circuit(resource_id)
            return response, {"display_name": "display_name", "ip_mtu": "ip_mtu", "bandwidth_shape_name": "bandwidth_shape_name", }    


class FileStorageHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'FileStorageClient' not in self._clients:
            from oci.file_storage import FileStorageClient
            self._clients['FileStorageClient'] = self.factory.create_client(FileStorageClient)

    def get_client(self, client_type):
        if client_type == 'FileStorageClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):

        if "mounttarget" not in resource_id.split(".") and "filesystem" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the FileStorageHandler: {resource_id}")
        
        self.initialize_clients()

        if "mounttarget" in resource_id.split("."):
            response = self.get_client('FileStorageClient').get_mount_target(resource_id)
            return  response, {"display_name": "display_name", "availability_domain": "AD", "observed_throughput": "current_throughput", "requested_throughput": "requested_throughput"}
        else:
            response = self.get_client('FileStorageClient').get_file_system(resource_id)
            return response, {"display_name": "display_name", "availability_domain": "AD"}


class InternetGatewayHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"

    def initialize_clients(self):
        if 'VirtualNetworkClient' not in self._clients:
            from oci.core import VirtualNetworkClient
            self._clients['VirtualNetworkClient'] = self.factory.create_client(VirtualNetworkClient)

    def get_client(self, client_type):
        if client_type == 'VirtualNetworkClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "internetgateway" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the InternetGatewayHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('VirtualNetworkClient').get_internet_gateway(resource_id)
        return response, {"display_name": "display_name"}


class LbaasHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'LoadBalancerClient' not in self._clients:
            from oci.load_balancer import LoadBalancerClient
            self._clients['LoadBalancerClient'] = self.factory.create_client(LoadBalancerClient)

    def get_client(self, client_type):
        if client_type == 'LoadBalancerClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "loadbalancer" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the LbaasHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('LoadBalancerClient').get_load_balancer(resource_id)
        return response, {"display_name": "display_name"}


class LoggingHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'LoggingManagementClient' not in self._clients:
            from oci.logging import LoggingManagementClient
            self._clients['LoggingManagementClient'] = self.factory.create_client(LoggingManagementClient)

    def get_client(self, client_type):
        if client_type == 'LoggingManagementClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        logGroupId = tags.get("logGroupId", None)

        if "log" not in resource_id.split(".") and logGroupId is None:
            raise ValueError(f"Unsupported resource ID for the LoggingHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('LoggingManagementClient').get_log(logGroupId, resource_id)
        return response, {"display_name": "display_name"}


class LustreFileSystemHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'LustreFileStorageClient' not in self._clients:
            from oci.lustre_file_storage import LustreFileStorageClient
            self._clients['LustreFileStorageClient'] = self.factory.create_client(LustreFileStorageClient)

    def get_client(self, client_type):
        if client_type == 'LustreFileStorageClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "lustrefilesystem" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the LustreFileSystemHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('LustreFileStorageClient').get_lustre_file_system(resource_id)
        return response, {"display_name": "display_name", "availability_domain": "AD", "performance_tier": "performance_tier", "capacity_in_gbs": "capacity_in_gbs"}


class ManagementAgentHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'ManagementAgentClient' not in self._clients:
            from oci.management_agent import ManagementAgentClient
            self._clients['ManagementAgentClient'] = self.factory.create_client(ManagementAgentClient)

    def get_client(self, client_type):
        if client_type == 'ManagementAgentClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "managementagent" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the ManagementAgentHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('ManagementAgentClient').get_management_agent(resource_id)
        return response, {"display_name": "display_name"}


class NatGatewayHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'VirtualNetworkClient' not in self._clients:
            from oci.core import VirtualNetworkClient
            self._clients['VirtualNetworkClient'] = self.factory.create_client(VirtualNetworkClient)

    def get_client(self, client_type):
        if client_type == 'VirtualNetworkClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "natgateway" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the NatGatewayHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('VirtualNetworkClient').get_nat_gateway(resource_id)
        return response, {"display_name": "display_name"}


class NLBHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'NetworkLoadBalancerClient' not in self._clients:
            from oci.network_load_balancer import NetworkLoadBalancerClient
            self._clients['NetworkLoadBalancerClient'] = self.factory.create_client(NetworkLoadBalancerClient)

    def get_client(self, client_type):
        if client_type == 'NetworkLoadBalancerClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "networkloadbalancer" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the NLBHandler: {resource_id}")
        
        self.initialize_clients()
        response = self.get_client('NetworkLoadBalancerClient').get_network_load_balancer(resource_id)
        return response, {"display_name": "display_name"}


class ObjectStorageHandler(ResourceHandler):
    """
    Handler for OCI Object Storage service resources (oci_objectstorage namespace).

    Handles object storage buckets. Uses the Resource Search service to find
    buckets by OCID, then fetches bucket details from the Object Storage client.
    This two-step approach is necessary because bucket IDs in metrics are OCIDs,
    but the Object Storage API requires namespace + bucket name.

    Note: The resource identifier key is "resourceID" (capital ID) rather than
    "resourceId" - this is a quirk of the object storage metric format.
    """

    def get_resource_identifier_key(self) -> str:
        return "resourceID"
    
    def initialize_clients(self):
        if 'ObjectStorageClient' not in self._clients:
            from oci.object_storage import ObjectStorageClient
            self._clients['ObjectStorageClient'] = self.factory.create_client(ObjectStorageClient)
        
        if 'ResourceSearchClient' not in self._clients:
            from oci.resource_search import ResourceSearchClient
            self._clients['ResourceSearchClient'] = self.factory.create_client(ResourceSearchClient)

    def get_client(self, client_type):
        if client_type == 'ObjectStorageClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        elif client_type == 'ResourceSearchClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        else:
            raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id: str, tags: Dict[str, Any]) -> Tuple[Any, Dict[str, str]]:
        """
        Get object storage bucket metadata.

        Uses a two-step process:
        1. Query Resource Search service to find bucket name from OCID
        2. Fetch bucket details from Object Storage client using namespace + bucket name

        Args:
            resource_id: OCID of the bucket
            tags: Metric tags (not used for object storage)

        Returns:
            Tuple of (get_bucket response, {"name": "display_name"})

        Raises:
            ValueError: If resource_id doesn't contain "bucket"
        """
        if "bucket" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the ObjectStorageHandler: {resource_id}")

        self.initialize_clients()

        # Step 1: Use Resource Search to find the bucket name from its OCID
        # Object Storage API requires namespace + bucket name, but we only have OCID
        from oci.resource_search.models import StructuredSearchDetails
        resource_search_response = self.get_client('ResourceSearchClient').search_resources(
            search_details=StructuredSearchDetails(
                type="Structured",
                query=f"query bucket resources where identifier='{resource_id}'"
            ),
            limit=1
        )

        # Step 2: If search succeeds, fetch bucket details using namespace and bucket name
        if resource_search_response.status == 200 and len(resource_search_response.data.items):
            bucket_name = resource_search_response.data.items[0].display_name
            namespace = self.get_client('ObjectStorageClient').get_namespace()

            response = self.get_client('ObjectStorageClient').get_bucket(namespace_name=namespace.data, bucket_name=bucket_name)
            return response, {"name": "display_name"}


class OKEHandler(ResourceHandler):
    """
    Handler for Oracle Container Engine for Kubernetes (OKE) resources.

    Handles both OKE control plane clusters and compute instances (worker nodes).
    Worker node instances are fetched via ComputeClient, while clusters are
    fetched via ContainerEngineClient. Determining which to fetch is based
    on the resource ID - it contains "instance" for nodes or "cluster" for clusters.
    """

    def get_resource_identifier_key(self) -> str:
        return "resourceId"
    
    def initialize_clients(self):
        if 'ContainerEngineClient' not in self._clients:
            from oci.container_engine import ContainerEngineClient
            self._clients['ContainerEngineClient'] = self.factory.create_client(ContainerEngineClient)

        if 'ComputeClient' not in self._clients:
            from oci.core import ComputeClient
            self._clients['ComputeClient'] = self.factory.create_client(ComputeClient)

    def get_client(self, client_type):
        if client_type == 'ComputeClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        elif client_type == 'ContainerEngineClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        else:
            raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "instance" not in resource_id.split(".") and "cluster" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the OKEHandler: {resource_id}")
        
        self.initialize_clients()

        if "instance" in resource_id.split("."):
            response = self.get_client('ComputeClient').get_instance(resource_id)
            return response, {"display_name": "display_name"}
        else:
            response = self.get_client('ContainerEngineClient').get_cluster(resource_id)
            return response, {"name": "display_name"}


class PostgresqlHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'PostgresqlClient' not in self._clients:
            from oci.psql import PostgresqlClient
            self._clients['PostgresqlClient'] = self.factory.create_client(PostgresqlClient)

    def get_client(self, client_type):
        if client_type == 'PostgresqlClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "postgresqldbsystem" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the PostgresqlHandler: {resource_id}")
        
        self.initialize_clients()

        response = self.get_client('PostgresqlClient').get_db_system(resource_id)
        return response, {"display_name": "display_name"}


class SecretHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'VaultsClient' not in self._clients:
            from oci.vault import VaultsClient
            self._clients['VaultsClient'] = self.factory.create_client(VaultsClient)

    def get_client(self, client_type):
        if client_type == 'VaultsClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "vaultsecret" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the SecretHandler: {resource_id}")
        
        self.initialize_clients()

        response = self.get_client('VaultsClient').get_secret(resource_id)
        return response, {"secret_name": "secret_name"}



class ServiceConnectorHubHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "connectorId"
    
    def initialize_clients(self):
        if 'ServiceConnectorClient' not in self._clients:
            from oci.sch import ServiceConnectorClient
            self._clients['ServiceConnectorClient'] = self.factory.create_client(ServiceConnectorClient)

    def get_client(self, client_type):
        if client_type == 'ServiceConnectorClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "serviceconnector" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the ServiceConnectorHubHandler: {resource_id}")
        
        self.initialize_clients()

        response = self.get_client('ServiceConnectorClient').get_service_connector(resource_id)
        return response, {"display_name": "display_name"}


class ServiceGatewayHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'VirtualNetworkClient' not in self._clients:
            from oci.core import VirtualNetworkClient
            self._clients['VirtualNetworkClient'] = self.factory.create_client(VirtualNetworkClient)

    def get_client(self, client_type):
        if client_type == 'VirtualNetworkClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "servicegateway" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the ServiceGatewayHandler: {resource_id}")
        
        self.initialize_clients()

        response = self.get_client('VirtualNetworkClient').get_service_gateway(resource_id)
        return response, {"display_name": "display_name"}



class VCNHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'VirtualNetworkClient' not in self._clients:
            from oci.core import VirtualNetworkClient
            self._clients['VirtualNetworkClient'] = self.factory.create_client(VirtualNetworkClient)

    def get_client(self, client_type):
        if client_type == 'VirtualNetworkClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "vnic" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the VCNHandler: {resource_id}")
        
        self.initialize_clients()

        response = self.get_client('VirtualNetworkClient').get_vnic(resource_id)
        return response, {"display_name": "display_name", "availability_domain": "AD", "private_ip": "private_ip", "public_ip": "public_ip"}


class VCNIPHandler(ResourceHandler):
    def get_resource_identifier_key(self):
        return "resourceId"
    
    def initialize_clients(self):
        if 'VirtualNetworkClient' not in self._clients:
            from oci.core import VirtualNetworkClient
            self._clients['VirtualNetworkClient'] = self.factory.create_client(VirtualNetworkClient)

    def get_client(self, client_type):
        if client_type == 'VirtualNetworkClient':
            if client_type not in self._clients:
                self.initialize_clients()
            return self._clients[client_type]
        raise ValueError(f"Unsupported client type: {client_type}")

    def get_resource(self, resource_id, tags):
        if "subnet" not in resource_id.split("."):
            raise ValueError(f"Unsupported resource ID for the VCNIPHandler: {resource_id}")
        
        self.initialize_clients()

        response = self.get_client('VirtualNetworkClient').get_subnet(resource_id)
        return response, {"display_name": "display_name"}


class OCIMetaClient:
    """
    Main client for fetching OCI resource metadata across multiple services.

    OCIMetaClient provides a unified interface for retrieving resource information
    from various OCI services. It maintains a registry of service-specific handlers
    and routes requests to the appropriate handler based on the metric namespace.

    This is the primary entry point for metric enrichment - given a namespace and
    resource tags, it fetches the corresponding OCI resource and returns both the
    API response and a mapping of resource attributes to metric tags.

    Attributes:
        factory (OCIClientFactory): Factory for creating OCI SDK clients
        handlers (dict): Registry of namespace -> ResourceHandler mappings

    Supported Namespaces:
        The client includes pre-registered handlers for:
        - oci_apigateway: API Gateway resources
        - oci_bastion: Bastion resources
        - oci_blockstore: Block and boot volumes
        - oci_compute*: Compute instances and infrastructure health
        - oci_fastconnect: FastConnect virtual circuits and cross-connects
        - oci_filestorage: File systems and mount targets
        - oci_internet_gateway: Internet gateways
        - oci_lbaas: Load balancers
        - oci_logging: Log resources
        - oci_lustrefilesystem: Lustre file systems
        - oci_managementagent: Management agents
        - oci_nat_gateway: NAT gateways
        - oci_nlb: Network load balancers
        - oci_objectstorage: Object storage buckets
        - oci_oke: Kubernetes clusters and nodes
        - oci_postgresql: PostgreSQL database systems
        - oci_secrets: Vault secrets
        - oci_service_connector_hub: Service connectors
        - oci_service_gateway: Service gateways
        - oci_vcn: VNICs and network resources
        - oci_vcnip: Subnets

    Usage Example:
        >>> from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
        >>> client = OCIMetaClient(config={}, signer=InstancePrincipalsSecurityTokenSigner())
        >>>
        >>> # Fetch compute instance metadata
        >>> tags = {"resourceId": "ocid1.instance.oc1.phx.example"}
        >>> response, attr_map = client.get_resource("oci_compute", tags)
        >>> print(f"Instance: {response.data.display_name}")
        >>> print(f"Attributes to tag: {attr_map}")
    """

    def __init__(self, **kwargs):
        """
        Initialize the OCI metadata client.

        Args:
            **kwargs: Keyword arguments passed to OCIClientFactory:
                - config (dict, optional): OCI configuration for config-based auth
                - signer: OCI authentication signer (config-based or instance principal)
                - retry_strategy (optional): Custom retry strategy for OCI SDK clients

        Example:
            >>> # Using instance principal authentication
            >>> from oci.auth.signers import InstancePrincipalsSecurityTokenSigner
            >>> client = OCIMetaClient(
            ...     config={},
            ...     signer=InstancePrincipalsSecurityTokenSigner()
            ... )
            >>>
            >>> # Using config file authentication
            >>> from oci.config import from_file
            >>> from oci import Signer
            >>> config = from_file()
            >>> signer = Signer.from_config(config)
            >>> client = OCIMetaClient(config=config, signer=signer)
        """
        self.factory = OCIClientFactory(
            config=kwargs.get("config"),
            signer=kwargs.get("signer"),
            retry_strategy=kwargs.get("retry_strategy")
        )

        # Register handlers for different namespaces
        # Note: Some namespaces share handlers (e.g., all compute* namespaces use ComputeHandler)
        self.handlers: Dict[str, ResourceHandler] = {
            "oci_apigateway": APIGatewayHandler(self.factory),
            "oci_bastion": BastionHandler(self.factory),
            "oci_blockstore": BlockStorageHandler(self.factory),
            "oci_compute": ComputeHandler(self.factory),
            "oci_compute_infrastructure_health": ComputeHandler(self.factory),
            "oci_compute_instance_health": ComputeHandler(self.factory),
            "oci_computeagent": ComputeHandler(self.factory),
            "gpu_infrastructure_health": ComputeHandler(self.factory),
            "rdma_infrastructure_health": ComputeHandler(self.factory),
            "oci_fastconnect": FastConnectHandler(self.factory),
            "oci_filestorage": FileStorageHandler(self.factory),
            "oci_internet_gateway": InternetGatewayHandler(self.factory),
            "oci_lbaas": LbaasHandler(self.factory),
            "oci_nlb": NLBHandler(self.factory),
            "oci_logging": LoggingHandler(self.factory),
            "oci_lustrefilesystem": LustreFileSystemHandler(self.factory),
            "oci_managementagent": ManagementAgentHandler(self.factory),
            "oci_nat_gateway": NatGatewayHandler(self.factory),
            "oci_objectstorage": ObjectStorageHandler(self.factory),
            "oci_oke": OKEHandler(self.factory),
            "oci_postgresql": PostgresqlHandler(self.factory),
            "oci_secrets": SecretHandler(self.factory),
            "oci_service_connector_hub": ServiceConnectorHubHandler(self.factory),
            "oci_service_gateway": ServiceGatewayHandler(self.factory),
            "oci_vcn": VCNHandler(self.factory),
            "oci_vcnip": VCNIPHandler(self.factory)
        }

    def get_namespaced_client(self, namespace: str) -> None:
        """
        Validate that a namespace has a registered handler.

        This method is primarily for validation purposes. It checks if the
        specified namespace is supported but does not return a client.

        Args:
            namespace: The OCI service namespace to validate

        Raises:
            ValueError: If the namespace is not supported (no handler registered)
        """
        if namespace not in self.handlers:
            raise ValueError(f"Unsupported namespace: {namespace}")


    def get_resource_ocid(self, namespace: str, tags: Dict[str, str]) -> str:
        """
        Extract the resource OCID from tags for a given namespace.

        Each handler specifies which tag key contains the resource OCID
        (via get_resource_identifier_key()). This method extracts that value.

        Args:
            namespace: The OCI service namespace
            tags: Metric tags dictionary containing resource identifiers

        Returns:
            The resource OCID extracted from tags

        Raises:
            ValueError: If namespace is unsupported or the identifier key is missing from tags
        """
        if namespace not in self.handlers:
            raise ValueError(f"Unsupported namespace: {namespace}")

        identifier_key = self.handlers[namespace].get_resource_identifier_key()
        resource_id = tags.get(identifier_key)

        if not resource_id:
            raise ValueError(f"Missing {identifier_key} in tags for namespace {namespace}")

        return resource_id

    def get_resource(self, namespace: str, tags: Dict[str, Any]) -> Tuple[Any, Dict[str, str]]:
        """
        Get resource information for the given namespace and tags.

        This is the main entry point for fetching OCI resource metadata.
        It routes the request to the appropriate handler based on namespace,
        extracts the resource OCID from tags, and returns both the API response
        and an attribute mapping for metric enrichment.

        Args:
            namespace: The OCI service namespace (e.g., "oci_compute", "oci_objectstorage")
            tags: Metric tags dictionary containing resource identifiers (e.g., {"resourceId": "ocid1..."})

        Returns:
            A tuple of (response, attribute_mapping):
            - response: OCI SDK response object with status, data, and other response fields
            - attribute_mapping: Dict mapping resource attributes to tag names
              Format: {"attribute_name": "tag_name"}
              Example: {"display_name": "display_name", "availability_domain": "AD"}

        Raises:
            ValueError: If namespace is unsupported or required identifier is missing
            Exception: For OCI SDK errors (propagated from handler)

        Example:
            >>> client = OCIMetaClient(config={}, signer=signer)
            >>> tags = {"resourceId": "ocid1.instance.oc1.phx.example"}
            >>> response, attr_map = client.get_resource("oci_compute", tags)
            >>> if response.status == 200:
            ...     print(f"Instance: {response.data.display_name}")
            ...     # Use attr_map to extract additional attributes as tags
        """
        try:
            if namespace not in self.handlers:
                raise ValueError(f"Unsupported namespace: {namespace}")

            resource_id = self.get_resource_ocid(namespace, tags)
            handler = self.handlers[namespace]

            return handler.get_resource(resource_id, tags)

        except Exception as e:
            logger.error(f"Error retrieving resource for namespace {namespace}: {str(e)}")
            raise

    def add_handler(self, namespace: str, handler: ResourceHandler) -> None:
        """
        Add or replace a custom handler for a namespace.

        Allows extending the client with support for additional OCI services
        or customizing behavior for existing namespaces.

        Args:
            namespace: The OCI service namespace to register
            handler: ResourceHandler instance for the namespace

        Example:
            >>> class CustomServiceHandler(ResourceHandler):
            ...     # Implement required abstract methods...
            ...
            >>> client = OCIMetaClient(config={}, signer=signer)
            >>> client.add_handler("oci_custom", CustomServiceHandler(client.factory))
        """
        self.handlers[namespace] = handler

    def get_supported_namespaces(self) -> list:
        """
        Return list of supported OCI service namespaces.

        Returns:
            List of namespace strings that have registered handlers

        Example:
            >>> client = OCIMetaClient(config={}, signer=signer)
            >>> namespaces = client.get_supported_namespaces()
            >>> print(f"Supported namespaces: {', '.join(namespaces)}")
        """
        return list(self.handlers.keys())