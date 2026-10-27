import configparser
import json
import os
import pathlib
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

import click
import lib.database as db
from ClusterShell.NodeSet import NodeSet
from ClusterShell.Task import task_self
from lib.functions import get_ansiblevars
from sqlalchemy import text


class Status(str, Enum):
    OK = "OK"
    FAIL = "FAIL"
    SKIP = "SKIP"

    def __str__(self):
        # StrEnum is 3.11+ and the repo targets 3.10; make str()/format
        # render the value ("OK") rather than "Status.OK".
        return self.value


@dataclass
class Check:
    name: str
    status: str
    detail: str = ""


INVENTORY_VARS = (
    "ldap",
    "slurm",
    "slurm_federation",
    "add_nfs",
    "shared_home",
    "nfs_source_IP",
    "slurm_backup_hostname",
    "queue_ocid",
)


def echo_header(title, no_color):
    color = None if no_color else "cyan"
    click.echo(click.style(f"\n{title}", fg=color, bold=True))


def echo_check(check, no_color):
    colors = {Status.OK: "green", Status.FAIL: "red", Status.SKIP: "yellow"}
    fg = None if no_color else colors.get(check.status)
    label = click.style(f"{check.status:>4}", fg=fg, bold=True)
    click.echo(f"{label}  {check.name:<40}  {check.detail}".rstrip())


def run_cmd(command, timeout=15):
    """Run a local command and return (returncode, stdout) without raising."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.returncode, result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)


def to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "yes", "1")


def load_inventory_vars(cluster_name, inventory_dir="/config/playbooks"):
    """Read health-relevant vars from the rendered Terraform inventory.

    Tries the cluster-specific inventory first, then the default one.
    Returns a dict of var name -> value (None when absent), or None when no
    inventory file can be read.
    """
    candidates = []
    if cluster_name:
        candidates.append(f"{inventory_dir}/inventory_{cluster_name}")
    candidates.append(f"{inventory_dir}/inventory")

    for path in candidates:
        if not pathlib.Path(path).exists():
            continue
        try:
            values = get_ansiblevars(path, INVENTORY_VARS)
        except (configparser.Error, OSError):
            continue
        return {var: values.get(var) for var in INVENTORY_VARS}
    return None


def check_database():
    try:
        with db.DBConn() as session:
            session.execute(text("SELECT 1"))
        return Check("clusterDB", Status.OK, "reachable")
    except Exception as exc:
        return Check("clusterDB", Status.FAIL, f"unreachable: {exc}")


def check_config_dirs(paths=("/config/bin", "/config/playbooks")):
    """Check that Terraform-copied repo assets exist under /config."""
    missing = [p for p in paths if not pathlib.Path(p).is_dir()]
    if missing:
        return Check("config dirs", Status.FAIL, f"missing {', '.join(missing)}")
    return Check("config dirs", Status.OK, ", ".join(paths))


# Ansible recap lines look like "PLAY RECAP" followed by per-host lines
# "host : ok=X changed=Y ... failed=Z ...". Bootstrap is complete only when
# the run reached its final marker. "fatal:" marks a failed task; note that
# "FAILED - RETRYING" lines are not failures and must not match.
# Terraform appends each bootstrap attempt to the same log, so only the
# latest attempt (after the last "Starting cluster configuration..." marker)
# is evaluated.
CONFIGURE_COMPLETE_MARKER = "Cluster configuration complete"
CONFIGURE_START_MARKER = "Starting cluster configuration..."
RECAP_FAILED_RE = re.compile(r"failed=[1-9]")
FATAL_TASK_RE = re.compile(r"^fatal: ", re.MULTILINE)
TAIL_SIZE = 64 * 1024


def check_initial_configure_log(path="/config/logs/initial_configure.log"):
    """Tail-scan the bootstrap log for failed tasks and completion marker.

    Only the latest attempt is evaluated: a failed earlier attempt followed by
    a successful retry reports Status.OK. Skipped when the log is absent (older
    deployments, or the file is only created on first bootstrap).
    """
    log = pathlib.Path(path)
    if not log.is_file():
        return Check("initial_configure.log", Status.SKIP, f"{path} not found")
    try:
        with log.open("r", errors="replace") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - TAIL_SIZE))
            tail = fh.read()
            if size > TAIL_SIZE and tail and not tail.endswith("\n"):
                # avoid matching a line cut in half at the seek boundary
                tail = tail.split("\n", 1)[-1]
    except OSError as exc:
        return Check("initial_configure.log", Status.FAIL, f"cannot read {path}: {exc}")

    attempt = tail.rsplit(CONFIGURE_START_MARKER, 1)[-1]

    if RECAP_FAILED_RE.search(attempt) or FATAL_TASK_RE.search(attempt):
        return Check("initial_configure.log", Status.FAIL, "failed tasks in bootstrap log")
    if CONFIGURE_COMPLETE_MARKER not in attempt:
        return Check(
            "initial_configure.log", Status.FAIL,
            "bootstrap did not reach 'Cluster configuration complete'",
        )
    return Check("initial_configure.log", Status.OK, "completed with no failed task")


# mgmt.log lines are written by lib.logger as "%(asctime)s - %(levelname)s - %(message)s"
# with local naive timestamps, so parse and compare them as local naive datetimes.
MGMT_LOG_TIME_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})"
)


def check_mgmt_log(path="/config/logs/mgmt.log", window=timedelta(minutes=5)):
    """Check that mgmt.log is readable and has no ERROR in the recent window."""
    log = pathlib.Path(path)
    if not log.is_file():
        return Check("mgmt.log", Status.SKIP, f"{path} not found")
    # mgmt.log timestamps are local time, like datetime.now() without tz.
    now = datetime.now(tz=timezone.utc).astimezone().replace(tzinfo=None)
    try:
        mtime = datetime.fromtimestamp(log.stat().st_mtime).astimezone().replace(tzinfo=None)
        with log.open("r", errors="replace") as fh:
            lines = fh.readlines()
    except OSError as exc:
        return Check("mgmt.log", Status.FAIL, f"cannot read {path}: {exc}")

    errors = []
    for line in lines:
        if " - ERROR - " not in line:
            continue
        match = MGMT_LOG_TIME_RE.match(line)
        if not match:
            errors.append(line)
            continue
        try:
            ts = datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}")
        except ValueError:
            errors.append(line)
            continue
        if now - ts <= window:
            errors.append(line)

    if errors:
        last = errors[-1].strip()
        return Check("mgmt.log", Status.FAIL, f"{len(errors)} recent ERROR(s), last: {last[:80]}")
    return Check(
        "mgmt.log", Status.OK,
        f"no ERROR in last {int(window.total_seconds() // 60)} min (modified {int((now - mtime).total_seconds() // 60)} min ago)",
    )


def check_service(name, units):
    """Check that at least one of the given systemd units is active."""
    units = (units,) if isinstance(units, str) else units
    for unit in units:
        rc, _out = run_cmd(["systemctl", "is-active", unit])
        if rc == 0:
            return Check(name, Status.OK, f"{unit} active")
    return Check(name, Status.FAIL, f"no active unit among {', '.join(units)}")


def sinfo_partitions():
    """Return (rc, sorted partition names) via sinfo JSON output.

    JSON is used instead of text formatting so partition names containing
    unusual characters cannot break parsing. The default partition is
    reported separately by check_default_partition.
    """
    rc, out = run_cmd(["sinfo", "--json"], timeout=30)
    if rc != 0 or not out:
        return rc, []
    try:
        data = json.loads(out)
        partitions = {entry["partition"]["name"] for entry in data.get("sinfo", [])}
    except (ValueError, KeyError, TypeError):
        return 1, []
    return 0, sorted(partitions)


def check_slurm_partitions():
    rc, partitions = sinfo_partitions()
    if rc != 0 or not partitions:
        return Check("slurm partitions", Status.FAIL, "sinfo returned no partitions")
    return Check("slurm partitions", Status.OK, ", ".join(partitions))


def check_default_partition():
    rc, out = run_cmd(["sinfo", "--json"], timeout=30)
    defaults = []
    if rc == 0 and out:
        try:
            data = json.loads(out)
            defaults = sorted(
                {
                    entry["partition"]["name"]
                    for entry in data.get("sinfo", [])
                    if "DEFAULT" in entry["partition"].get("flags", [])
                }
            )
        except (ValueError, KeyError, TypeError):
            defaults = []
    if rc != 0 or not defaults:
        return Check(
            "default partition", Status.FAIL,
            "no default partition; job submission requires -p",
        )
    return Check("default partition", Status.OK, ", ".join(defaults))


def check_disk_space(paths=("/",), threshold=90):
    worst, worst_path = 0, None
    for path in paths:
        rc, out = run_cmd(["df", "-P", path])
        if rc != 0 or len(out.splitlines()) < 2:
            return Check("disk space", Status.FAIL, f"df failed for {path}")
        try:
            pct = int(out.splitlines()[1].split()[4].rstrip("%"))
        except (IndexError, ValueError):
            return Check("disk space", Status.FAIL, f"unparseable df output for {path}")
        if pct > worst:
            worst, worst_path = pct, path
    status = Status.FAIL if worst >= threshold else Status.OK
    detail = f"{worst_path} at {worst}%"
    if status == Status.FAIL:
        detail += f"; threshold {threshold}%"
    return Check("disk space", status, detail)


def findmnt(path, probe_timeout=5):
    """Return (probe_rc, fstype, source) for the nfs mount at path, following autofs.

    /home is mounted with x-systemd.automount, so findmnt reports an autofs
    entry and the nfs entry once the mount is triggered. Probe the directory
    via a subprocess (an in-process os.listdir would block indefinitely on an
    unresponsive hard-mounted NFS share), then prefer the nfs line.
    probe_rc is the probe's return code: non-zero means the mount exists but
    is unresponsive (e.g. hard-mounted NFS server down), and callers should
    report it even though findmnt still lists the mount.
    """
    probe_rc, _ = run_cmd(["ls", path], timeout=probe_timeout)
    rc, out = run_cmd(["findmnt", "-n", "-o", "FSTYPE,SOURCE", path], timeout=probe_timeout)
    if rc != 0 or not out:
        return probe_rc, None, None
    lines = [line.split(None, 1) for line in out.splitlines() if line.strip()]
    for parts in lines:
        if parts[0] == "nfs":
            return probe_rc, parts[0], (parts[1].strip() if len(parts) > 1 else "")
    parts = lines[0]
    source = parts[1].strip() if len(parts) > 1 else ""
    return probe_rc, parts[0], source


def check_nfs_mount(name, path, expected_source=None):
    probe_rc, fstype, source = findmnt(path)
    if probe_rc != 0:
        detail = f"{path} unresponsive (probe rc={probe_rc}"
        detail += ", mount hung)" if fstype else ", not mounted)"
        return Check(name, Status.FAIL, detail)
    if fstype is None:
        return Check(name, Status.FAIL, f"{path} is not mounted")
    if fstype != "nfs":
        return Check(name, Status.FAIL, f"{path} is {fstype}, expected nfs")
    if expected_source and not source.startswith(str(expected_source)):
        return Check(name, Status.FAIL, f"{path} from {source}, expected {expected_source}")
    return Check(name, Status.OK, f"{path} from {source}")


def check_home_export():
    # exportfs needs root to read /var/lib/nfs/etab; as a regular user it
    # exits 0 with no output.
    rc, out = run_cmd(["sudo", "-n", "exportfs", "-v"])
    exported = rc == 0 and any(
        line.split() and line.split()[0].rstrip("/") == "/home"
        for line in out.splitlines()
    )
    if exported:
        return Check("home export", Status.OK, "/home exported by controller")
    return Check("home export", Status.FAIL, "/home not exported by controller")


def check_mgmt():
    checks = []
    _rc, enabled = run_cmd(["systemctl", "is-enabled", "mgmt.timer"])
    _rc, active = run_cmd(["systemctl", "is-active", "mgmt.timer"])
    timer_ok = enabled == "enabled" and active == "active"
    timer_detail = f"enabled={enabled or 'unknown'}, active={active or 'unknown'}"
    checks.append(
        Check("mgmt.timer", Status.OK if timer_ok else Status.FAIL, timer_detail)
    )
    _rc, out = run_cmd(
        ["systemctl", "show", "mgmt.service", "--property=Result", "--value"]
    )
    checks.append(
        Check(
            "mgmt.service last run",
            Status.OK if out == "success" else Status.FAIL,
            f"result={out or 'unknown'}",
        )
    )
    return checks


def remote_output(host, command, timeout=20):
    """Run a command on a remote host over ssh, return (ok, stdout)."""
    task = task_self()
    task.flush_buffers()
    try:
        task.run(command, nodes=NodeSet(host), timeout=timeout)
    except Exception:
        return False, None
    ok = task.max_retcode() == 0
    output = None
    for buf, _nodes in task.iter_buffers():
        if not isinstance(buf, (bytes, bytearray)):
            buf = bytes(buf)
        output = buf.decode(errors="replace").strip()
        break
    return ok, output


def check_munge_key(host, key_path="/etc/munge/munge.key"):
    """Compare the controller's munge key hash against a remote host."""
    name = f"backup {host} munge key"
    rc, out = run_cmd(["sudo", "-n", "md5sum", key_path])
    if rc != 0 or not out:
        return Check(name, Status.FAIL, "cannot read local munge key")
    local_hash = out.split()[0]
    ok, out = remote_output(host, f"sudo -n md5sum {key_path}")
    if not ok or not out:
        return Check(name, Status.FAIL, "cannot read remote munge key")
    if out.split()[0] != local_hash:
        return Check(name, Status.FAIL, "munge key differs from controller")
    return Check(name, Status.OK, "matches controller")


def check_backup_controller(host, slurm_enabled, ldap_enabled):
    prefix = f"backup {host} "
    reachable, _ = remote_output(host, "hostname")
    if not reachable:
        return [Check(f"{prefix.strip()}", Status.FAIL, "unreachable")]

    checks = [Check(f"{prefix.strip()}", Status.OK, "reachable")]

    if slurm_enabled:
        checks.append(check_munge_key(host))

    units = []
    if slurm_enabled:
        # slurmdbd always runs on the backup: slurm.conf points
        # AccountingStorageBackupHost at it even under federation.
        units += ["slurmctld", "slurmdbd", "slurmrestd", "munge"]
    if ldap_enabled:
        units += ["slapd", "sssd"]
    if not units:
        return checks

    _, out = remote_output(host, f"systemctl is-active {' '.join(units)}")
    if out is None:
        checks += [Check(f"{prefix}{unit}", Status.FAIL, "no systemctl output") for unit in units]
        return checks
    states = out.splitlines()
    for idx, unit in enumerate(units):
        state = states[idx].strip() if idx < len(states) else None
        checks.append(
            Check(f"{prefix}{unit}", Status.OK if state == "active" else Status.FAIL, state or "no output")
        )
    return checks

