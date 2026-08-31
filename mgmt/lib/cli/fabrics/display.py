from rich.table import Table
from rich.console import Console


def _short_ocid_tail(value, length=5):
    if not value:
        return "None"
    value = str(value)
    if len(value) <= length:
        return value
    return f"...{value[-length:]}"


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
                if fabric[2]:
                    mc_lines = "\n".join(f"{k}: {v}" for k, v in fabric[2].items())
                else:
                    mc_lines = "0"
                table.add_row("memory_clusters", mc_lines)
                for i in fabric[3].keys():
                    table.add_row(i, str(fabric[3][i]))
                console.print(table)
        else:
            table = Table(title="Fabrics")
            attributes1 = ["id","lifecycle_state","fabric_health"]

            for attr in attributes1:
                table.add_column(attr, justify="left", no_wrap=(attr == "id"))
            table.add_column("localblock", justify="left", no_wrap=True)
            table.add_column("gpu_memory_clusters", justify="left", no_wrap=True)
            for i in fabric_list[0][3].keys():
                table.add_column(i, justify="left")
            for fabric in fabric_list:
                row = [str(getattr(fabric[0], attr)) for attr in attributes1]
                row.append(_short_ocid_tail(getattr(fabric[0], "compute_local_block_id", None)))
                if fabric[2]:
                    row.append("\n".join(fabric[2].keys()))
                else:
                    row.append("0")
                for i in fabric[3].keys():
                    row.append(str(fabric[3][i]))
                table.add_row(*row)
            console.print(table)
    else:
        console.print("No fabrics found")
