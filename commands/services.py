import asyncio
import socket
from pathlib import Path

import psutil

from core.auth import auth
from core.utils import send_long_message


def _lan_ip() -> str:
    """Return the host's primary LAN IPv4 address, or '127.0.0.1' if offline.

    Uses the UDP-socket trick: connect() on a UDP socket only resolves which
    interface would route to the destination — no packets are sent.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _scan() -> list[tuple[int, str, int, str]]:
    """Return [(pid, name, port, cwd)] for current-user TCP listeners on ports >= 1024.

    De-dupes on (pid, port) so an IPv4+IPv6 dual bind shows once.
    """
    me = psutil.Process().username()
    seen: set[tuple[int, int]] = set()
    results: list[tuple[int, str, int, str]] = []

    for proc in psutil.process_iter(["pid", "name", "username"]):
        try:
            if proc.info["username"] != me:
                continue
            for conn in proc.net_connections(kind="tcp"):
                if conn.status != psutil.CONN_LISTEN or not conn.laddr:
                    continue
                port = conn.laddr.port
                if port < 1024:
                    continue
                pid = proc.info["pid"]
                key = (pid, port)
                if key in seen:
                    continue
                seen.add(key)
                try:
                    cwd = proc.cwd()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    cwd = "?"
                results.append((pid, proc.info["name"], port, cwd))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return results


def _shorten_home(path: str) -> str:
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def _format(ip: str, entries: list[tuple[int, str, int, str]]) -> str:
    """Render the user-facing message.

    entries: [(pid, name, port, cwd)] — already de-duped.
    Sorted ascending by port. Cwd shortened with `~` if under $HOME.
    """
    if not entries:
        return "No services listening."

    header = f"Services on {ip}:"
    if ip == "127.0.0.1":
        header += " (no LAN interface detected)"

    lines = [header, ""]
    for pid, name, port, cwd in sorted(entries, key=lambda e: e[2]):
        lines.append(f" {port:<5} {name:<15} pid {pid}")
        lines.append(f"       http://{ip}:{port}")
        lines.append(f"       {_shorten_home(cwd)}")
        lines.append("")
    return "\n".join(lines).rstrip()


COMMAND = "services"
DESCRIPTION = "List local services running on this machine"


@auth
async def handler(update, context):
    loop = asyncio.get_running_loop()
    try:
        ip, entries = await asyncio.gather(
            loop.run_in_executor(None, _lan_ip),
            loop.run_in_executor(None, _scan),
        )
        await send_long_message(update, _format(ip, entries))
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
