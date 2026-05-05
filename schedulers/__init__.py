import importlib
from pathlib import Path


def discover():
    """Yield (name, scheduled_handler, schedule_times, schedule_days) for each scheduler plugin."""
    schedulers_dir = Path(__file__).parent
    for path in sorted(schedulers_dir.glob("*.py")):
        if path.stem == "__init__":
            continue
        module = importlib.import_module(f"schedulers.{path.stem}")
        if hasattr(module, "scheduled_handler") and hasattr(module, "SCHEDULE_TIMES"):
            yield (
                path.stem,
                module.scheduled_handler,
                module.SCHEDULE_TIMES,
                getattr(module, "SCHEDULE_DAYS", (0, 1, 2, 3, 4)),
            )
