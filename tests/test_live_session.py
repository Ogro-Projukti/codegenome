"""Security regression tests for the live HTTP session."""

from __future__ import annotations

import http.client
import ipaddress
import json
from pathlib import Path

import pytest

from codegenome.live_session import LiveSession, LiveSessionConfig
from codegenome.network_utils import get_lan_ip


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


def test_unauthenticated_ai_chat_is_unreachable_from_secondary_interface(
    tmp_path: Path,
) -> None:
    """SEC-01: loopback binding must refuse the same port on a LAN interface."""
    secondary_ip = get_lan_ip()
    if ipaddress.ip_address(secondary_ip).is_loopback:
        pytest.skip("No secondary IPv4 interface is available on this host")

    session = LiveSession(LiveSessionConfig(workspace=tmp_path, http_port=0))
    try:
        session.start_http_server()
        assert session._httpd is not None
        _bound_host, bound_port = session._httpd.server_address
        connection = http.client.HTTPConnection(secondary_ip, bound_port, timeout=3)
        try:
            try:
                connection.request(
                    "POST",
                    "/ai/chat",
                    body=json.dumps({"message": "unauthenticated SEC-01 probe"}),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
            except OSError:
                return
            assert response.status == 401
        finally:
            connection.close()
    finally:
        session.stop()
