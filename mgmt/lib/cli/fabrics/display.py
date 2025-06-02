from rich.table import Table
from rich.console import Console

def print_fabrics(fabric_list, full=False):
    if full:
        for fabric in fabric_list:
            table = Table(show_header=False, show_lines=True)
            table.add_column(justify="left")
            table.add_column(justify="left")
            for attr in dir(fabric[0]):
                if attr.startswith("_") or attr[0].lower() != attr[0]:
                    continue
                table.add_row(attr, str(getattr(fabric[0], attr)))
            table.add_row("size", str(fabric[1]))
            table.add_row("cluster_name", str(fabric[2]))
            table.add_row("cluster_id", str(fabric[3]))
            console = Console()
            console.print(table)

    else:
        table = Table(title="Fabrics")
        attributes = ["display_name","lifecycle_state","fabric_health","id","healthy_host_count"]
        for attr in attributes:
            if attr == "id":
                table.add_column(attr, justify="left", no_wrap=True)
            else:
                table.add_column(attr, justify="left")
        table.add_column("Cluster", justify="left")
        table.add_column("Running", justify="left")
        table.add_column("Available", justify="left")
        for fabric in fabric_list:
            row = [str(getattr(fabric[0], attr)) for attr in attributes]
            row.append(str(fabric[2]))
            row.append(str(fabric[1]))
            row.append(str(int(getattr(fabric[0], attr))-fabric[1]))
            table.add_row(*row)
        console = Console()
        console.print(table)