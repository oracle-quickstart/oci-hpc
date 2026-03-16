from rich.table import Table
from rich.console import Console

def print_fabrics(fabric_list, full=False):
    console = Console()
    if fabric_list:
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
                table.add_row("memory_cluster_name", str(fabric[2]))
                table.add_row("memory_cluster_id", str(fabric[3]))
                for i in fabric[4].keys():
                    table.add_row(i, str(fabric[4][i]))
                console.print(table)
        else:
            table = Table(title="Fabrics")
            attributes1 = ["id","lifecycle_state","fabric_health"]
            attributes2 = ["memory_cluster"]
            for attr in attributes1+attributes2:
                if attr == "id" or attr == "memory_cluster":
                    table.add_column(attr, justify="left", no_wrap=True)
                else:
                    table.add_column(attr, justify="left")
            for i in fabric_list[0][4].keys():
                table.add_column(i, justify="left")
            for fabric in fabric_list:
                row = [str(getattr(fabric[0], attr)) for attr in attributes1]
                row.append(str(fabric[2]))
                for i in fabric[4].keys():
                    row.append(str(fabric[4][i]))
                table.add_row(*row)
            console.print(table)
    else:
        console.print("No fabrics found")
