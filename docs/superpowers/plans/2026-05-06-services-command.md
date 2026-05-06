# `/services` Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/services` Telegram command that lists user-owned TCP listeners on ports ≥ 1024, showing port, process, PID, LAN URL, and cwd.

**Architecture:** Single new plugin file `commands/services.py` with four pure helper functions (`_lan_ip`, `_listeners`, `_cwd`, `_format`) plus an async `handler` that orchestrates them. Auto-discovered by `commands/__init__.py` — no other files change.

**Tech Stack:** Python 3, `subprocess` to invoke `lsof`, `socket` for LAN IP detection, `python-telegram-bot` (already in project), `asyncio.run_in_executor` for blocking calls.

**Note on tests:** The repo has no automated test suite (consistent with `commands/portfolio.py` etc.). Each task verifies behavior via `python3 -c "..."` one-liners run from the repo root, plus a final manual end-to-end test through Telegram.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `commands/services.py` | Create | All logic for the new command — helpers + handler |

No other files modified. Auto-discovery in `commands/__init__.py` picks up the new plugin on bot restart.

---

### Task 1: LAN IP detection helper

**Files:**
- Create: `commands/services.py`

- [ ] **Step 1: Create the file with `_lan_ip()`**

Write `commands/services.py`:

```python
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
```

- [ ] **Step 2: Verify the function returns a plausible IP**

Run from the repo root (`/Users/zl/works/tg-bot`):

```bash
python3 -c "from commands.services import _lan_ip; print(_lan_ip())"
```

Expected: prints an IPv4 like `192.168.x.x` or `10.x.x.x` (or `127.0.0.1` if offline). Should NOT raise.

- [ ] **Step 3: Commit**

```bash
git add commands/services.py
git commit -m "feat(services): add LAN IP detection helper"
```

---

### Task 2: TCP listener parser

**Files:**
- Modify: `commands/services.py`

- [ ] **Step 1: Add `_listeners()`**

Append to `commands/services.py`:

```python
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
```

- [ ] **Step 2: Start a known test listener in the background**

```bash
python3 -m http.server 8765 >/dev/null 2>&1 &
echo $! > /tmp/services_test_pid
```

- [ ] **Step 3: Verify the listener is found**

```bash
python3 -c "from commands.services import _listeners; print([e for e in _listeners() if e[2] == 8765])"
```

Expected: prints a single tuple like `[(<some pid>, 'python3.11', 8765)]`. The pid should match `cat /tmp/services_test_pid`.

- [ ] **Step 4: Stop the test listener**

```bash
kill "$(cat /tmp/services_test_pid)" && rm /tmp/services_test_pid
```

- [ ] **Step 5: Verify it disappears**

```bash
python3 -c "from commands.services import _listeners; print([e for e in _listeners() if e[2] == 8765])"
```

Expected: prints `[]`.

- [ ] **Step 6: Commit**

```bash
git add commands/services.py
git commit -m "feat(services): add TCP listener parser via lsof"
```

---

### Task 3: Cwd lookup helper

**Files:**
- Modify: `commands/services.py`

- [ ] **Step 1: Add `_cwd()`**

Append to `commands/services.py`:

```python
def _cwd(pid: int) -> str:
    """Return the working directory of `pid`, or '?' if it can't be determined.

    The `-a` flag is critical: lsof ORs selectors by default, so `-p PID -d cwd`
    would dump cwd info for every process. `-a` makes the selectors AND-ed.
    """
    try:
        out = subprocess.check_output(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return "?"
    for line in out.splitlines():
        if line.startswith("n"):
            return line[1:]
    return "?"
```

- [ ] **Step 2: Verify it returns a real path for the current shell**

```bash
python3 -c "import os; from commands.services import _cwd; print(_cwd(os.getppid()))"
```

Expected: prints an absolute directory path (likely `/Users/zl/works/tg-bot` or your shell's cwd). NOT `?`.

- [ ] **Step 3: Verify it returns `?` for a bogus pid**

```bash
python3 -c "from commands.services import _cwd; print(_cwd(999999))"
```

Expected: prints `?`.

- [ ] **Step 4: Commit**

```bash
git add commands/services.py
git commit -m "feat(services): add cwd lookup helper"
```

---

### Task 4: Output formatting

**Files:**
- Modify: `commands/services.py`

- [ ] **Step 1: Add `_format()` and the home-shortening helper**

Append to `commands/services.py`:

```python
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
```

- [ ] **Step 2: Verify formatting with a fixed input**

```bash
python3 -c '
from commands.services import _format
entries = [
    (4821, "node", 3000, "/Users/zl/works/my-frontend"),
    (7890, "python3.11", 8000, "/Users/zl/works/tg-bot"),
    (312, "postgres", 5432, "/usr/local/var/postgres"),
]
print(_format("192.168.1.42", entries))
'
```

Expected output (note: ascending port order, `~` shortening for paths under `/Users/zl`):

```
Services on 192.168.1.42:

 3000  node            pid 4821
       http://192.168.1.42:3000
       ~/works/my-frontend

 8000  python3.11      pid 7890
       http://192.168.1.42:8000
       ~/works/tg-bot

 5432  postgres        pid 312
       http://192.168.1.42:5432
       /usr/local/var/postgres
```

(The 5432 entry comes last only if its port is highest — re-order the input list above so the printed result really is sorted ascending: 3000, 5432, 8000.)

- [ ] **Step 3: Verify empty state**

```bash
python3 -c "from commands.services import _format; print(_format('192.168.1.42', []))"
```

Expected: `No services listening.`

- [ ] **Step 4: Verify offline header annotation**

```bash
python3 -c '
from commands.services import _format
print(_format("127.0.0.1", [(1, "x", 3000, "/tmp")]))
'
```

Expected: first line is `Services on 127.0.0.1: (no LAN interface detected)`.

- [ ] **Step 5: Commit**

```bash
git add commands/services.py
git commit -m "feat(services): add output formatter"
```

---

### Task 5: Wire up the async command handler

**Files:**
- Modify: `commands/services.py`

- [ ] **Step 1: Add the imports, plugin metadata, and handler**

Append to `commands/services.py`:

```python
import asyncio

from core.auth import auth
from core.utils import send_long_message

COMMAND = "services"
DESCRIPTION = "List local services running on this machine"


@auth
async def handler(update, context):
    loop = asyncio.get_event_loop()
    try:
        ip, raw = await asyncio.gather(
            loop.run_in_executor(None, _lan_ip),
            loop.run_in_executor(None, _listeners),
        )
        unique_pids = sorted({pid for pid, _, _ in raw})
        cwds = await asyncio.gather(*[
            loop.run_in_executor(None, _cwd, pid) for pid in unique_pids
        ])
        cwd_by_pid = dict(zip(unique_pids, cwds))
        entries = [(pid, cmd, port, cwd_by_pid[pid]) for pid, cmd, port in raw]
        await send_long_message(update, _format(ip, entries))
    except FileNotFoundError:
        await update.message.reply_text("lsof not found — install via Xcode CLT or brew")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
```

- [ ] **Step 2: Verify the plugin is auto-discovered**

```bash
python3 -c "
from commands import discover
names = [c[0] for c in discover()]
print('services' in names, names)
"
```

Expected: prints `True` followed by the list of all commands including `services`.

- [ ] **Step 3: Start the bot in a separate terminal**

```bash
python3 bot.py
```

Wait until you see the bot has started. Leave it running.

- [ ] **Step 4: In a second terminal, start a test listener**

```bash
python3 -m http.server 8765 >/dev/null 2>&1 &
echo $! > /tmp/services_test_pid
```

- [ ] **Step 5: From Telegram, send `/services` to the bot**

Expected: a reply listing TCP listeners owned by your user on ports ≥ 1024, including port 8765 with `python3.11` and the cwd from which the test listener was started. The header shows `Services on <your LAN IP>:`. Entries are sorted ascending by port.

- [ ] **Step 6: Stop the test listener and re-send `/services`**

```bash
kill "$(cat /tmp/services_test_pid)" && rm /tmp/services_test_pid
```

Expected: the 8765 entry is gone from the new reply.

- [ ] **Step 7: Stop the bot** (Ctrl-C in its terminal)

- [ ] **Step 8: Commit**

```bash
git add commands/services.py
git commit -m "feat(services): wire up /services command handler"
```

---

### Task 6: Verify error paths and update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Verify the lsof-missing error path**

Without uninstalling lsof, simulate it by hiding it from PATH:

```bash
PATH=/usr/bin:/bin python3 -c "
import os
print('lsof on PATH:', any(os.path.exists(os.path.join(p, 'lsof')) for p in os.environ['PATH'].split(':')))
from commands.services import _listeners
try:
    _listeners()
    print('UNEXPECTED: no error')
except FileNotFoundError as e:
    print('OK: FileNotFoundError raised:', e)
"
```

Expected: `lsof on PATH: False` then `OK: FileNotFoundError raised: ...`. (On most macOS systems lsof lives in `/usr/sbin`, which the trimmed PATH excludes.)

If `lsof on PATH:` prints `True` for your system, find where `lsof` lives (`which lsof`) and rerun with a `PATH` that excludes that directory.

- [ ] **Step 2: Add `/services` to the README command table**

In `README.md`, find the command table (lines ~29-41) and add a new row alphabetically between `/screen` and `/sentiment`:

```
| `/services` | List local services running on this machine |
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document /services command in README"
```

---

## Self-Review

**Spec coverage:**
- User-owned listeners ≥ 1024 → Task 2 (`_listeners` uses `-u $(id -u)` and filters port < 1024)
- Per-entry: port, command, pid, LAN URL, cwd → Tasks 2, 3, 4 (collected, formatted)
- Loopback shown with LAN IP, no special marking → Task 4 (`_format` always uses `ip` parameter — no per-entry branching on bind address)
- Sort by port ascending → Task 4 (`sorted(entries, key=lambda e: e[2])`)
- Plugin auto-discovery → Task 5 (verified in Step 2)
- LAN IP via UDP-socket trick → Task 1
- Async via `run_in_executor` → Task 5
- `lsof` not on PATH → Task 5 (handler `FileNotFoundError`), Task 6 (verified)
- `lsof` non-zero exit (other than 1) → Task 5 (handler generic `Exception`)
- Process exits between calls → Task 3 (`_cwd` returns `?`)
- IPv4 + IPv6 dual bind → Task 2 (`seen` set keyed on `(pid, port)`)
- Offline (LAN IP = 127.0.0.1) → Task 4 (header annotation)
- Empty state → Task 4 (`No services listening.`)
- README updated → Task 6

**Placeholder scan:** No TBD/TODO/"add error handling" in the plan. Every code step contains complete, runnable code.

**Type consistency:** `_listeners()` returns `list[tuple[int, str, int]]` (pid, command, port); `_cwd(pid: int) -> str`; `_format(ip: str, entries: list[tuple[int, str, int, str]])` (pid, command, port, cwd). The handler in Task 5 builds the 4-tuple by joining `_listeners` output with `_cwd` results — types align.
