"""Security regression tests for the live HTTP session."""

from __future__ import annotations

import ipaddress
from pathlib import Path

from codegenome.live_session import LiveSession, LiveSessionConfig


def test_live_http_server_binds_loopback_by_default(tmp_path: Path) -> None:
    """The unauthenticated live UI must not be reachable from LAN by default."""
    session = LiveSession(LiveSessionConfig(workspace=tmp_path, http_port=0))

    try:
        session.start_http_server()
        assert session._httpd is not None
        bound_host, _ = session._httpd.server_address
        assert ipaddress.ip_address(bound_host).is_loopback
        assert bound_host == session.bind_host == "127.0.0.1"
    finally:
        session.stop()
