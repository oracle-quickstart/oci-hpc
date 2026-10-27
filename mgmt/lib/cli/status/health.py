import socket

import click
import lib.database as db
from lib.cli.status.checks import (
    Check,
    Status,
    check_backup_controller,
    check_config_dirs,
    check_database,
    check_default_partition,
    check_disk_space,
    check_home_export,
    check_initial_configure_log,
    check_mgmt,
    check_mgmt_log,
    check_nfs_mount,
    check_service,
    check_slurm_partitions,
    echo_check,
    echo_header,
    load_inventory_vars,
    to_bool,
)


def render_health(no_color):
    """
    Check control plane health of the cluster

    Verifies that the services and mounts required for nodes to join the
    cluster and for jobs to be accepted are healthy: Slurm services, shared
    filesystems, LDAP (if configured), the backup controller (if configured)
    and the mgmt automation itself. Reads the expected topology from the
    inventory file under /config/playbooks.

    Returns True when all checks pass, False when any check fails.
    """
    checks = []

    echo_header("========= OCI-HPC Control Plane Health =========", no_color)
    click.echo(f"Controller  : {socket.gethostname()}")

    checks.append(check_database())
    try:
        controller = db.get_controller_node()
    except Exception:
        controller = None
    cluster_name = controller.cluster_name if controller else None
    inventory = load_inventory_vars(cluster_name)

    if inventory is None:
        checks.append(
            Check("inventory", Status.FAIL, "no readable inventory under /config/playbooks")
        )
        inventory = {}

    slurm_enabled = to_bool(inventory.get("slurm"), default=True)
    slurm_federation = to_bool(inventory.get("slurm_federation"), default=False)
    ldap_enabled = to_bool(inventory.get("ldap"), default=False)
    add_nfs = to_bool(inventory.get("add_nfs"), default=False)
    shared_home = (inventory.get("shared_home") or "").strip().lower()
    nfs_source_ip = (inventory.get("nfs_source_IP") or "").strip()
    backup_hostname = (inventory.get("slurm_backup_hostname") or "").strip()

    echo_header("Controller services", no_color)
    checks.append(check_config_dirs())
    checks.append(check_initial_configure_log())
    for check in checks:
        echo_check(check, no_color)

    service_checks = []
    if slurm_enabled:
        slurm_units = ["slurmctld", "slurmrestd", "munge"]
        if slurm_federation:
            # federated clusters use external accounting; no local slurmdbd
            service_checks.append(
                Check("slurmdbd", Status.SKIP, "slurm_federation enabled; external accounting")
            )
        else:
            slurm_units.insert(1, "slurmdbd")
        service_checks += [check_service(unit, unit) for unit in slurm_units]
        service_checks.append(check_slurm_partitions())
        service_checks.append(check_default_partition())
    else:
        service_checks.append(Check("slurm services", Status.SKIP, "slurm disabled"))
    service_checks.append(check_service("mysql", ("mysqld", "mariadb")))
    if ldap_enabled:
        service_checks += [check_service(unit, unit) for unit in ("slapd", "sssd")]
    else:
        service_checks += [
            Check(unit, Status.SKIP, "ldap disabled in inventory")
            for unit in ("slapd", "sssd")
        ]
    service_checks.append(check_disk_space())
    for check in service_checks:
        echo_check(check, no_color)
    checks += service_checks

    echo_header("Shared filesystems", no_color)
    mount_checks = [
        check_nfs_mount("config mount", "/config"),
    ]
    if shared_home == "fss" and add_nfs:
        mount_checks.append(
            check_nfs_mount("home mount", "/home", expected_source=nfs_source_ip)
        )
    elif shared_home == "nfs":
        mount_checks.append(check_service("nfs server", ("nfs-server", "nfs-kernel-server")))
        mount_checks.append(check_home_export())
    elif shared_home == "fss":
        # site.yml only mounts /home on the controller when add_nfs is set.
        mount_checks.append(
            Check("home mount", Status.SKIP, "shared_home=fss without add_nfs; /home is local")
        )
    else:
        mount_checks.append(
            Check("home mount", Status.SKIP, f"shared_home={shared_home or 'unset'}; /home is local")
        )
    for check in mount_checks:
        echo_check(check, no_color)
    checks += mount_checks

    echo_header("Backup controller", no_color)
    if backup_hostname:
        backup_checks = check_backup_controller(
            backup_hostname, slurm_enabled, ldap_enabled
        )
    else:
        backup_checks = [Check("backup controller", Status.SKIP, "not configured")]
    for check in backup_checks:
        echo_check(check, no_color)
    checks += backup_checks

    echo_header("mgmt automation", no_color)
    mgmt_checks = check_mgmt()
    mgmt_checks.append(
        Check(
            "queue_ocid",
            Status.OK if (inventory.get("queue_ocid") or "").strip() else Status.FAIL,
            (inventory.get("queue_ocid") or "").strip() or "missing in inventory",
        )
    )
    mgmt_checks.append(check_mgmt_log())
    for check in mgmt_checks:
        echo_check(check, no_color)
    checks += mgmt_checks

    passed = sum(1 for c in checks if c.status == Status.OK)
    failed = sum(1 for c in checks if c.status == Status.FAIL)
    skipped = sum(1 for c in checks if c.status == Status.SKIP)

    summary_color = "red" if failed else "green"
    summary = click.style(
        f"\nSummary: {passed} passed, {failed} failed, {skipped} skipped",
        fg=None if no_color else summary_color,
        bold=True,
    )
    click.echo(summary)

    return failed == 0
