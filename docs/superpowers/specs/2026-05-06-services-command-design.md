# `/services` command — design

## Goal

Add a Telegram bot command that lists local services running on the bot's host machine, so the user can see at a glance which dev servers / projects are up, on which port, and in which directory.

## User-facing behavior

Command: `/services`
Description (in `/help`): `List local services running on this machine`

The bot replies with a list of TCP listeners owned by the current user, on ports ≥ 1024, sorted by port ascending. Each entry shows the port, process name, PID, a LAN URL, and the process's working directory.

### Example output

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

Empty state: `No services listening.`

## Scope decisions

| Decision | Choice | Reason |
|---|---|---|
| Which listeners count | TCP listeners owned by the current user, ports ≥ 1024 | Filters out OS daemons and root-owned services without hand-maintaining a port list. |
| Per-entry detail | port, process name, PID, LAN URL, cwd | Cwd disambiguates multiple `node`/`python` processes — answers "what's that?" |
| Loopback-only services | Show with the LAN IP in the URL (no special marking) | User explicitly requested this. URL won't work from another device for `127.0.0.1`-bound processes, but the user accepts this. |
| Sort order | Port ascending | Most natural for scanning. |

## Architecture

### File layout

One new file: `commands/services.py`. No changes to `bot.py` or `commands/__init__.py` — the existing plugin auto-discovery picks it up.

```python
COMMAND = "services"
DESCRIPTION = "List local services running on this machine"

@auth
async def handler(update, context):
    ...
```

### Data collection

Three pieces of data are needed: listening sockets, cwd per process, host LAN IP.

**1. Listening sockets** — single `lsof` call:

```
lsof -nP -iTCP -sTCP:LISTEN -u <uid> -F pcn
```

- `-n -P` skip name resolution.
- `-iTCP -sTCP:LISTEN` filter to TCP listeners.
- `-u <uid>` (where `<uid>` = `os.getuid()`) restricts to current-user processes.
- `-F pcn` emits machine-parseable records — one field per line, tagged `p<pid>`, `c<command>`, `n<bind:port>`.

Ports < 1024 are filtered in Python after parsing.

**2. Cwd per process** — one `lsof` call per unique pid:

```
lsof -a -p <pid> -d cwd -Fn
```

The `-a` flag is critical: by default `lsof` ORs its selectors, so `-p PID -d cwd` would dump cwd info for every process. `-a` makes the selectors AND-ed. Parse out the `n<path>` line. If the call fails (process exited between calls), use `?` as the cwd.

**3. LAN IP** — UDP-socket trick:

```python
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
ip = s.getsockname()[0]
s.close()
```

No packets are actually sent — `connect` on a UDP socket just resolves which interface would route to the destination. More reliable on macOS than `socket.gethostbyname(socket.gethostname())`, which often returns `127.0.0.1`.

If this returns `127.0.0.1` (e.g. offline), still render the list and append `(no LAN interface detected)` to the header.

### Async pattern

`lsof` and the UDP-socket call are blocking. Wrap them in `loop.run_in_executor(None, ...)` — same pattern as `commands/portfolio.py`. The handler stays `async`.

### Output

Built as a list of strings, joined with `\n`, sent via `core.utils.send_long_message` (already used for handling Telegram's 4096-char cap).

Cwd is shortened with `~` if it starts with the user's home directory.

## Error handling & edge cases

| Case | Behavior |
|---|---|
| `lsof` not on PATH | Reply: `lsof not found — install via Xcode CLT or brew` |
| `lsof` errors (non-zero exit, unreadable output) | Reply: `Error: <message>` — matches `portfolio.py` pattern |
| Process exits between the two `lsof` calls | That row's cwd is `?`; rest of list renders normally |
| Same port appears twice (IPv4 + IPv6 bind by same pid) | Dedupe by `(pid, port)` |
| LAN IP detection returns `127.0.0.1` (offline) | Render normally; header shows `(no LAN interface detected)` |
| No listeners after filtering | Reply: `No services listening.` |

## Out of scope

- UDP listeners
- Docker container port mappings
- HTTP probing to identify projects from response content
- Caching — calls are cheap, run fresh each time
- Cross-platform support beyond macOS — the bot's documented host. `lsof` is also present on most Linux distros, but no extra effort spent verifying portability.

## Testing

Manual verification on macOS:

1. Start a dummy listener: `python3 -m http.server 8765` in `~/some-test-dir`.
2. Send `/services` to the bot.
3. Confirm the entry appears with correct port, process, cwd, and LAN URL.
4. Stop the listener; resend `/services`; confirm it disappears.
5. With nothing user-owned listening on ≥ 1024, confirm `No services listening.` reply.

No automated tests — consistent with the rest of the repo, which has none.
