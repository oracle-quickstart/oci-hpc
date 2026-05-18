import click
import math
from typing import Any
from collections import Counter, defaultdict
import lib.database as db
import lib.functions as func
from dataclasses import dataclass

###
# Helper functions
###

BASTION_ROLES = {"login", "monitoring", "controller", "backup"}

def percent(n: int, d: int) -> int:
    if d <= 0:
        return 0
    return int(round((n / d) * 100))

def bar(n: int, d: int, width: int = 18) -> str:
    if d <= 0:
        return " " * width
    filled = int(math.floor((n / d) * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)

def is_configured(node: dict[str, Any]) -> bool:
    compute_status = str(node.get("compute_status") or "").lower()
    controller_status = str(node.get("controller_status") or "").lower()
    return compute_status == "configured" or controller_status == "configured"

def is_running(node: dict[str, Any]) -> bool:
    return str(node.get("status") or "").lower() == "running"

def category_for_role(role: str | None) -> str:
    r = (role or "unknown").strip().lower()
    return "bastion" if r in BASTION_ROLES else r

def health_bucket(node: dict[str, Any]) -> str:
    role = str(node.get("role") or "").lower()
    if role in BASTION_ROLES:
        return "healthy" if (is_running(node) and is_configured(node)) else "needs-attn"

    rec = str(
        node.get("healthcheck_recommendation")
        or node.get("active_healthcheck_recommendation")
        or ""
    ).strip()

    rec_norm = rec.lower()

    if rec_norm in ("", "none", "null"):
        return "healthy" if (is_running(node) and is_configured(node)) else "needs-attn"
    if "healthy" in rec_norm:
        return "healthy"
    return "needs-attn"
    
def get_avail_nodes(cluster_block):

    available_nodes = 0
    repair_nodes = 0
    controller = db.get_controller_node()


    if controller is None:
        return None, None

    # get the list of hosts from host api
    host_api_list = func.get_host_api_dict(controller.compartment_id,controller.tenancy_id)

    if not len(host_api_list):
        return None, None

    # sort the list down to just the ones from the specified clusterid
    cluster_hosts = [
        host for host in host_api_list 
        if host.network_block_id == cluster_block
    ]


    for host_api in cluster_hosts:
        # Only consider hosts without an instance_id
        if host_api.instance_id is None:
            # Available: no instance_id AND lifecycle_state is AVAILABLE
            if host_api.lifecycle_state == "AVAILABLE":
                available_nodes += 1
            # Repair: no instance_id AND lifecycle_state is NOT AVAILABLE
            else:
                repair_nodes += 1

    return available_nodes, repair_nodes

@dataclass
class ClusterSummary:
    cluster_name: str
    cluster_block: str
    nodes_total: int
    nodes_running: int
    nodes_configured: int
    ad_counts: Counter[str]
    role_total: Counter[str]
    role_configured: Counter[str]
    role_running: Counter[str]
    health_buckets: Counter[str]
    avail_nodes: int
    repair_nodes: int

def summarize_cluster(cluster: str, nodes: list[dict[str, Any]], cluster_block) -> ClusterSummary:
    ad_counts: Counter[str] = Counter()
    role_total: Counter[str] = Counter()
    role_configured: Counter[str] = Counter()
    role_running: Counter[str] = Counter()
    health_buckets: Counter[str] = Counter()
    nodes_running = 0
    nodes_configured = 0
    avail_nodes = 0
    repair_nodes = 0

    for n in nodes:
        ad = str(n.get("availability_domain") or "")
        ad_counts[ad] += 1
        cat = category_for_role(n.get("role"))
        role_total[cat] += 1
        if is_configured(n):
            role_configured[cat] += 1
            nodes_configured += 1
        if is_running(n):
            role_running[cat] += 1
            nodes_running += 1

        health_buckets[health_bucket(n)] += 1

    avail_nodes,repair_nodes = get_avail_nodes(cluster_block)

    return ClusterSummary(
        cluster_name=cluster,
        cluster_block=cluster_block,
        nodes_total=len(nodes),
        nodes_running=nodes_running,
        nodes_configured=nodes_configured,
        ad_counts=ad_counts,
        role_total=role_total,
        role_configured=role_configured,
        role_running=role_running,
        health_buckets=health_buckets,
        avail_nodes=avail_nodes,
        repair_nodes=repair_nodes
    )


def render_status(nodes, no_color: bool):

    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    tenancy_ids: set[str] = set()
    needs_attention = []
    compartment_ids: set[str] = set()
    controller_names: set[str] = set()
    shapes: Counter[str] = Counter()

    # Define all colors based on no_color flag
    if no_color:
        black = None
        red = None
        green = None
        yellow = None
        blue = None
        magenta = None
        cyan = None
        white = None
    else:
        black = "black"
        red = "red"
        green = "green"
        yellow = "yellow"
        blue = "blue"
        magenta = "magenta"
        cyan = "cyan"
        white = "white"

    # Format and display status heading
    heading = click.style("\n========= OCI-HPC Cluster Status ==========", fg=cyan, bold=True)
    utc_now = click.style(str(db.current_utc_time()), fg=blue, bold=True)

    click.echo(heading+"\nGenerated: "+utc_now+"\n")

    for n in nodes:
        clusters[str(n.get("cluster_name"))].append(n)
        if n.get("tenancy_id"):
            tenancy_ids.add(str(n.get("tenancy_id")))
        if n.get("compartment_id"):
            compartment_ids.add(str(n.get("compartment_id")))
        if n.get("controller_name"):
            controller_names.add(str(n.get("controller_name")))
        if n.get("shape"):
            shapes[str(n.get("shape"))] += 1
        if health_bucket(n) == "needs-attn":
            needs_attention.append(n)

    summaries = [summarize_cluster(name, ns, ns[0].get("network_block_id")) for name, ns in clusters.items()]

    for tid in sorted(tenancy_ids):
        click.echo(f"Tenancy     : {tid}")
    for cid in sorted(compartment_ids):
        click.echo(f"Compartment : {cid}")
    if shapes:
        click.echo("Shapes      : "+', '.join(f"{key} (qty: {value})" for key, value in shapes.items()))
    click.echo("")

    if len(clusters) > 1  and len(nodes) > 1:
        click.echo(f"Cluster Overview ({len(clusters)} clusters, {len(nodes)} nodes)\n")
    elif  len(clusters) < 2  and len(nodes) > 1: 
        click.echo(f"Cluster Overview ({len(clusters)} cluster, {len(nodes)} nodes)\n")
    elif  len(clusters) > 1  and len(nodes) < 2: 
        click.echo(f"Cluster Overview ({len(clusters)} clusters, {len(nodes)} node)\n")
    else : 
        click.echo(f"Cluster Overview ({len(clusters)} cluster, {len(nodes)} node)\n")

    # Get cluster/node details
    # Cluster header
    
    cluster_header = f"{'CLUSTER':20} {'NODES':29} {'HEALTH':22} {'CAPACITY (avail|repair)':24} {'AD':15} "
    click.echo(cluster_header)


    for s in summaries:

        nodes_col = f"total: {s.nodes_total} ({s.nodes_configured} cfg|{s.nodes_running} run)"

        healthy = s.health_buckets.get("healthy", 0)

        health_percent = percent(healthy, s.nodes_total)
        health_color = green if health_percent > 94 else yellow
        if health_percent < 80 :
            health_color = red

        health_bar = click.style(bar(healthy, s.nodes_total, 14), fg=health_color)
        health_bar = f"{health_bar} {health_percent}%"
        roles_col = f"compute: {s.role_configured.get('compute', 0)} bastion: {s.role_configured.get('bastion', 0)}"
        ads = ",".join(s.ad_counts.keys())
        capacity_col = f"{s.avail_nodes}|{s.repair_nodes}"

        row = (
        f"{str(s.cluster_name or ''):20} "
        f"{str(nodes_col or ''):29} " 
        f"{str(health_bar or ''):31} "
        f"{str(capacity_col or ''):24} "
        f"{str(ads or ''):15}"
        )

        click.echo(row)

    if len(needs_attention) > 0 :
        needs_attention_heading = click.style(f"\nNodes needing attention ({len(needs_attention)})", fg=yellow)
        click.echo(needs_attention_heading)
        click.echo("+++++++++++++++++++++++++++\n")
        needs_attention_header = click.style(f"{'HOSTNAME':22} {'CLUSTER':15} {'STATUS':15} {'SLURM STATE':12} {'RECOMMENDATION'}", fg=yellow)
        click.echo(needs_attention_header)

        for n in needs_attention :
            hostname = click.style("n['hostname']", fg=yellow)
            row = (
            f"{str(n.get('hostname') or ''):<22} "
            f"{str(n.get('cluster_name') or ''):15} "
            f"{str(n.get('status') or ''):15} "
            f"{str(n.get('slurm_state') or ''):12} "
            f"{str(n.get('healthcheck_recommendation') or '')}"
            )
            click.echo(row)

        click.echo("\nHint: Run 'mgmt recommendations list' for more details")

