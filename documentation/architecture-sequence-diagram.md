# OCI HPC Cluster Network - Architecture Diagram

This document describes the architecture and execution flow of the OCI HPC Cluster Network Terraform and Ansible stack. It reflects the current repository implementation.

## Sequence Diagrams

### 1. Terraform Apply - Complete Provisioning Flow

Shows how Terraform creates the core network, shared storage, event resources, and controller configuration in a single apply.

```mermaid
sequenceDiagram
    autonumber
    participant User as User/CI
    participant TF as Terraform
    participant OCI as OCI APIs
    participant FSS as File Storage
    participant Reg as Container Registry
    participant Func as Functions Service
    participant Events as Events Service
    participant Queue as Queue Service
    participant Ctrl as Controller Instance

    User->>TF: terraform apply

    rect rgb(230, 240, 255)
        Note over TF,OCI: Phase 1: Network Infrastructure
        TF->>OCI: Create VCN, subnets, security rules, and DNS resources
        OCI-->>TF: Network resource IDs
    end

    rect rgb(230, 255, 240)
        Note over TF,FSS: Phase 2: Shared Storage
        TF->>FSS: Create or configure File Storage resources
        TF->>FSS: Create /config export
        FSS-->>TF: config FSS hostname
    end

    rect rgb(255, 240, 230)
        Note over TF,Queue: Phase 3: Event Infrastructure
        TF->>Reg: Create or use Function image repository
        TF->>TF: Build, mirror, or push Function image as configured
        TF->>Func: Create Functions application and write_node_function
        TF->>Queue: Create queue (120-second visibility timeout)
        TF->>Events: Create launchinstance.end rule
        TF->>Events: Create terminateinstance.begin rule
    end

    rect rgb(255, 230, 255)
        Note over TF,Ctrl: Phase 4: Controller Bootstrap
        TF->>OCI: Create controller instance
        OCI-->>TF: instance ID and IP
        TF->>Ctrl: Mount /config from config FSS
        TF->>Ctrl: Copy playbooks, bin, conf, samples, and scripts
        TF->>Ctrl: Execute bin/controller.sh (60-minute timeout)
        Ctrl->>Ctrl: Install OS, Python, and Ansible dependencies
        TF->>Ctrl: Execute bin/configure.sh (2-hour timeout)
        Ctrl->>Ctrl: Run playbooks/site.yml
    end

    TF-->>User: Apply complete
```

### 2. Controller Setup Detail

Shows the controller bootstrap scripts and the initial `site.yml` configuration that establishes controller services.

```mermaid
sequenceDiagram
    autonumber
    participant TF as Terraform Provisioner
    participant Ctrl as Controller Instance
    participant Pkg as Package Manager
    participant Ansible as Ansible
    participant FSS as Config FSS
    participant SLURM as Slurm

    TF->>Ctrl: remote-exec: bin/controller.sh

    rect rgb(240, 240, 240)
        Note over Ctrl,Pkg: controller.sh execution
        Ctrl->>Ctrl: Wait for cloud-init completion
        Ctrl->>Ctrl: Source setup_environment.sh
        Ctrl->>Pkg: Install OS packages
        Ctrl->>Pkg: Install Python packages and Ansible
        Ctrl-->>TF: controller.sh complete
    end

    TF->>Ctrl: remote-exec: bin/configure.sh

    rect rgb(230, 255, 230)
        Note over Ctrl,SLURM: configure.sh → site.yml
        Ctrl->>Ctrl: Prepare inventory and /etc/ansible/hosts
        Ctrl->>Ansible: ansible-playbook site.yml
        Ansible->>FSS: Configure shared home when FSS is selected
        Ansible->>Ctrl: Configure MySQL, mgmt, monitoring, and services
        Ansible->>SLURM: Configure controller and Slurm services
        Ansible-->>Ctrl: site.yml complete
        Ctrl-->>TF: configure.sh complete
    end
```

### 3. Compute Node Boot Sequence

Shows how a compute node uses instance metadata to mount `/config` and run its role-specific Ansible bootstrap.

```mermaid
sequenceDiagram
    autonumber
    participant OCI as OCI Compute
    participant Node as Compute Node
    participant IMDS as Instance Metadata Service
    participant FSS as Config FSS
    participant Script as compute.sh
    participant Ansible as Ansible

    OCI->>Node: Launch instance with cloud-init.sh user data

    rect rgb(240, 248, 255)
        Note over Node,IMDS: cloud-init.sh execution
        Node->>Node: Detect OS and default user
        Node->>IMDS: Read freeform tags individually
        IMDS-->>Node: controller_name, cluster_name, config_fss_hostname, role tags
        Node->>Node: Select compute.sh unless login, monitoring, or controller
    end

    rect rgb(255, 248, 240)
        Note over Node,FSS: Mount /config
        Node->>Node: Replace stale /config fstab entry
        Node->>Node: Add config_fss_hostname:/config to /etc/fstab
        loop Until mount and bootstrap files are ready
            Node->>FSS: Mount /config
            FSS-->>Node: Shared bootstrap files
            Node->>Node: Verify selected role script and helpers
        end
    end

    rect rgb(240, 255, 240)
        Note over Node,Ansible: compute.sh execution
        Node->>Script: Execute /config/bin/compute.sh cluster_name
        Script->>Script: Run environment, OS, Python, and Ansible setup scripts
        Script->>Ansible: Run compute.yml with inventory_cluster_name
        Ansible->>Node: Configure mgmt, Slurm client, storage, RDMA/GPU, and monitoring roles
        Ansible-->>Script: compute.yml complete
    end
```

### 4. Instance Launch Event - Runtime Flow

Shows how an instance launch event updates DNS and records a newly starting node through the Function, queue, and `mgmt` service.

```mermaid
sequenceDiagram
    autonumber
    participant OCI as OCI Compute
    participant Events as OCI Events
    participant Func as write_node_function
    participant DNS as Private DNS Zone
    participant Queue as OCI Queue
    participant Mgmt as mgmt services run
    participant DB as mgmt database

    OCI->>Events: Emit launchinstance.end
    Events->>Func: Invoke with event payload

    rect rgb(230, 245, 255)
        Note over Func,DNS: Function execution
        Func->>Func: Extract resource ID, compartment ID, and event type
        Func->>OCI: Get instance and verify controller_name tag
        alt Tag matches
            Func->>OCI: Read primary VNIC, private IP, and subnet CIDR
            Func->>Func: Use defined_hostname or derive hostname from subnet index
            Func->>DNS: Create or update A record
            Func->>OCI: Update display name when hostname_convention is set
        else Tag does not match
            Func-->>Events: Return without queue message
        end
    end

    rect rgb(230, 255, 230)
        Note over Func,DB: Queue and management processing
        Func->>Queue: Put starting message on controller_name channel
        Mgmt->>Queue: Read controller_name channel
        Mgmt->>DB: Create node with status=starting and controller_status=configuring
        Mgmt->>Queue: Delete message
    end
```

### 5. Instance Terminate Event - Runtime Flow

Shows how a termination event removes the DNS record and marks the corresponding node as terminating in the management database.

```mermaid
sequenceDiagram
    autonumber
    participant User as User/Autoscaler
    participant OCI as OCI Compute
    participant Events as OCI Events
    participant Func as write_node_function
    participant DNS as Private DNS Zone
    participant Queue as OCI Queue
    participant Mgmt as mgmt services run
    participant DB as mgmt database

    User->>OCI: Terminate instance request
    OCI->>Events: Emit terminateinstance.begin
    Events->>Func: Invoke with event payload

    rect rgb(255, 240, 240)
        Note over Events,DNS: Function execution
        Func->>OCI: Get instance and verify controller_name tag
        alt Tag matches
            Func->>Func: Use current instance display name
            Func->>DNS: Delete A record
            Func->>Queue: Put terminating message on controller_name channel
        else Tag does not match
            Func-->>Events: Return without queue message
        end
    end

    rect rgb(255, 245, 230)
        Note over Mgmt,DB: Management processing
        Mgmt->>Queue: Read controller_name channel
        Mgmt->>DB: Mark node controller and compute status terminating
        Mgmt->>Queue: Delete message
    end

    OCI->>OCI: Instance termination completes
```

### 6. Login/Monitoring Node Boot Sequence

Shows how role metadata selects the login or monitoring bootstrap and its corresponding Ansible playbook.

```mermaid
sequenceDiagram
    autonumber
    participant OCI as OCI Compute
    participant Node as Login/Monitoring Node
    participant IMDS as Instance Metadata Service
    participant FSS as Config FSS
    participant Ansible as Ansible

    OCI->>Node: Launch instance with cloud-init.sh user data
    Node->>IMDS: Read role and config FSS tags
    IMDS-->>Node: login, monitoring, cluster_name, config_fss_hostname
    Node->>FSS: Mount /config and verify bootstrap files

    alt login=true
        rect rgb(230, 255, 230)
            Note over Node,Ansible: Login node setup
            Node->>Node: Execute /config/bin/login.sh
            Node->>Ansible: Run login.yml
            Ansible->>Node: Configure mgmt, SSH, storage, and login services
        end
    else monitoring=true
        rect rgb(255, 245, 230)
            Note over Node,Ansible: Monitoring node setup
            Node->>Node: Execute /config/bin/monitoring.sh
            Node->>Ansible: Run monitoring.yml
            Ansible->>Node: Configure monitoring, mgmt, and dashboard services
        end
    end
```

### 7. Complete End-to-End Flow

Shows the relationship between provisioning, compute bootstrap, event-driven management state, Slurm job execution, and scale down.

```mermaid
sequenceDiagram
    autonumber
    participant User as User
    participant TF as Terraform
    participant Ctrl as Controller
    participant Pool as Compute Capacity
    participant Node as Compute Node
    participant Events as OCI Events
    participant Func as Function
    participant Queue as Queue
    participant Mgmt as mgmt
    participant DB as mgmt database
    participant SLURM as Slurm

    rect rgb(240, 240, 255)
        Note over User,Ctrl: Provisioning phase
        User->>TF: terraform apply
        TF->>TF: Create network, storage, Function, Events, and queue
        TF->>Ctrl: Create and configure controller with site.yml
        TF->>Pool: Create configured compute capacity
    end

    rect rgb(240, 255, 240)
        Note over Pool,DB: Compute registration
        Pool->>Node: Launch compute instance
        par Node bootstrap
            Node->>Node: cloud-init.sh mounts /config
            Node->>Node: compute.sh runs compute.yml
            Node->>SLURM: slurmd joins configured cluster
        and Event processing
            Node->>Events: launchinstance.end
            Events->>Func: Invoke
            Func->>Func: Verify controller tag and update DNS/display name
            Func->>Queue: Write starting message
            Mgmt->>Queue: Read controller channel
            Mgmt->>DB: Create configuring node record
        end
    end

    rect rgb(255, 250, 240)
        Note over User,SLURM: Job execution
        User->>SLURM: sbatch job.sh
        SLURM->>Node: Allocate and run job
        Node-->>SLURM: Job complete
    end

    rect rgb(255, 240, 240)
        Note over Pool,DB: Scale down
        Pool->>Node: Terminate instance
        Node->>Events: terminateinstance.begin
        Events->>Func: Invoke
        Func->>Func: Delete DNS record
        Func->>Queue: Write terminating message
        Mgmt->>Queue: Read controller channel
        Mgmt->>DB: Mark node terminating
    end
```

### 8. Function (func.py) Internal Flow

Shows the Function's tag validation, hostname and DNS processing, and controller-channel queue write for each event type.

```mermaid
sequenceDiagram
    autonumber
    participant Event as OCI Event
    participant Handler as handler()
    participant WMQ as write_message_queue()
    participant GTC as get_tag_controller()
    participant Net as get_instance_network_info()
    participant DNS as update_dns()
    participant UDN as update_display_name()
    participant OCI as OCI APIs
    participant Queue as OCI Queue

    Event->>Handler: Invoke with payload
    Handler->>Handler: Extract resource ID, compartment ID, and event type
    Handler->>WMQ: write_message_queue(...)
    WMQ->>GTC: Get instance and check controller_name tag
    GTC->>OCI: get_instance(instance_ocid)
    OCI-->>GTC: Instance details and freeform tags

    alt controller_name tag matches
        GTC-->>WMQ: Hostname settings and cluster name
        alt launchinstance.end
            WMQ->>DNS: update_dns(instance_launch=True)
            DNS->>Net: Get primary VNIC private IP and subnet CIDR
            Net->>OCI: list_vnic_attachments, get_vnic, get_subnet
            Net-->>DNS: private IP and CIDR
            DNS->>DNS: Choose defined hostname or derive subnet index
            DNS->>OCI: update_rr_set(A record)
            DNS-->>WMQ: hostname and private IP
            opt hostname_convention is set
                WMQ->>UDN: update_display_name(instance_ocid, hostname)
                UDN->>OCI: Wait for RUNNING, then update instance display name
            end
            WMQ->>WMQ: Build starting message
        else terminateinstance.begin
            WMQ->>DNS: update_dns(instance_launch=False)
            DNS->>OCI: delete_rr_set(A record)
            DNS-->>WMQ: hostname
            WMQ->>WMQ: Build terminating message
        end
        WMQ->>OCI: Get queue messages endpoint
        WMQ->>Queue: put_messages(channel_id=controller_name)
        Queue-->>WMQ: Message accepted
    else tag does not match
        WMQ-->>Handler: Return without queue message
    end

    Handler-->>Event: Empty success response
```
