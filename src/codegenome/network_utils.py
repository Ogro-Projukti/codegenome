"""Network helpers for LAN-accessible services."""

from __future__ import annotations

import socket


def get_lan_ip() -> str:
    """Return the primary LAN IPv4 address for this machine.

    Uses a UDP connect trick to discover the outbound interface IP without
    sending traffic. Falls back to ``127.0.0.1`` when detection fails.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
