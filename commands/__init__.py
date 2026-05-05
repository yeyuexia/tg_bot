import importlib
from pathlib import Path


def discover():
    """Yield (command_name, handler_fn, description, module) for each command plugin."""
    commands_dir = Path(__file__).parent
    for path in sorted(commands_dir.glob("*.py")):
        if path.stem == "__init__":
            continue
        module = importlib.import_module(f"commands.{path.stem}")
        if hasattr(module, "COMMAND") and hasattr(module, "handler"):
            yield module.COMMAND, module.handler, getattr(module, "DESCRIPTION", ""), module

