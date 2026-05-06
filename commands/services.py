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
