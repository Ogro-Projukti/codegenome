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


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if ``port`` can be bound on ``host`` right now.

    The probe binds a throwaway socket without ``SO_REUSEADDR`` so that a port
    still held by a lingering process (the common cause of ``WinError 10048``)
    is correctly reported as unavailable.

    Args:
        port (int): TCP port to probe.
        host (str): Interface to probe against. Defaults to loopback.

    Returns:
        bool: True when the port is free, False when it is already in use.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def find_free_port(
    preferred: int, host: str = "127.0.0.1", *, attempts: int = 50
) -> int:
    """Return a bindable port, preferring ``preferred`` then scanning upward.

    Args:
        preferred (int): The first port to try.
        host (str): Interface the port must be bindable on.
        attempts (int): How many sequential ports to try before giving up.

    Returns:
        int: A port that was bindable at probe time.

    Raises:
        OSError: If no free port is found within ``attempts``.
    """
    probe_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    for candidate in range(preferred, preferred + max(1, attempts)):
        if is_port_available(candidate, probe_host):
            return candidate
    raise OSError(
        f"No free port found in range {preferred}-{preferred + attempts - 1} "
        f"on {probe_host}."
    )
