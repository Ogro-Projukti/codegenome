"""Tests for network utility helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from codegenome.network_utils import get_lan_ip


def test_get_lan_ip_returns_detected_address() -> None:
    mock_socket = MagicMock()
    mock_socket.__enter__.return_value = mock_socket
    mock_socket.__exit__.return_value = False
    mock_socket.getsockname.return_value = ("192.168.1.50", 54321)

    with patch("codegenome.network_utils.socket.socket", return_value=mock_socket):
        assert get_lan_ip() == "192.168.1.50"

    mock_socket.connect.assert_called_once_with(("8.8.8.8", 80))


def test_get_lan_ip_falls_back_to_loopback() -> None:
    mock_socket = MagicMock()
    mock_socket.__enter__.return_value = mock_socket
    mock_socket.__exit__.return_value = False
    mock_socket.connect.side_effect = OSError("no route")

    with patch("codegenome.network_utils.socket.socket", return_value=mock_socket):
        assert get_lan_ip() == "127.0.0.1"
