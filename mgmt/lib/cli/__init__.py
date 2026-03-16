import pkgutil
from importlib import import_module

"""
To add a new Click subcommand, create a module (either a single file or a
directory) and make a function named "cmd" decorated as a click group or
command. The subcommand name is the first argument to the group/command
decorator.

e.g.

@click.group("foo")
def cmd():
    ...

or

@click.command("bar")
def cmd():
    ...

manage.py will then import the subcommands list and add each one to the
top-level click group.

There are a bunch of other ways we could have automatically loaded subcommands,
but this is what I tried first and it worked.
"""

subcommands = []
for modinfo in pkgutil.iter_modules(__path__):
    module = import_module(f"{__name__}.{modinfo.name}")
    try:
        subcommands.append(getattr(module, "cmd"))
    except AttributeError:
        pass
