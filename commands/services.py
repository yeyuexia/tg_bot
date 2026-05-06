import socket


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


import os
import subprocess


def _listeners() -> list[tuple[int, str, int]]:
    """Return [(pid, command, port)] for current-user TCP listeners on ports >= 1024.

    De-dupes on (pid, port) so an IPv4+IPv6 dual bind shows once.
    """
    uid = os.getuid()
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-u", str(uid), "-F", "pcn"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as e:
        # lsof exits 1 when nothing matches — treat as empty
        if e.returncode == 1:
            return []
        raise

    results: list[tuple[int, str, int]] = []
    pid: int | None = None
    cmd: str | None = None
    seen: set[tuple[int, int]] = set()

    for line in out.splitlines():
        if not line:
            continue
        tag, val = line[0], line[1:]
        if tag == "p":
            pid = int(val)
            cmd = None
        elif tag == "c":
            cmd = val
        elif tag == "n" and pid is not None and cmd is not None:
            # val examples: "*:3000", "127.0.0.1:5432", "[::1]:8080"
            port_str = val.rsplit(":", 1)[-1]
            try:
                port = int(port_str)
            except ValueError:
                continue
            if port < 1024:
                continue
            key = (pid, port)
            if key in seen:
                continue
            seen.add(key)
            results.append((pid, cmd, port))
    return results


def _cwd(pid: int) -> str:
    """Return the working directory of `pid`, or '?' if it can't be determined."""
    try:
        out = subprocess.check_output(
            ["lsof", "-p", str(pid), "-d", "cwd", "-Fn"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return "?"
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return "?"


from pathlib import Path


def _shorten_home(path: str) -> str:
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def _format(ip: str, entries: list[tuple[int, str, int, str]]) -> str:
    """Render the user-facing message.

    entries: [(pid, command, port, cwd)] — already de-duped.
    Sorted ascending by port. Cwd shortened with `~` if under $HOME.
    """
    if not entries:
        return "No services listening."

    header = f"Services on {ip}:"
    if ip == "127.0.0.1":
        header += " (no LAN interface detected)"

    lines = [header, ""]
    for pid, cmd, port, cwd in sorted(entries, key=lambda e: e[2]):
        lines.append(f" {port:<5} {cmd:<15} pid {pid}")
        lines.append(f"       http://{ip}:{port}")
        lines.append(f"       {_shorten_home(cwd)}")
        lines.append("")
    return "\n".join(lines).rstrip()
