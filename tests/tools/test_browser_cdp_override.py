from unittest.mock import Mock, patch


HOST = "example-host"
PORT = 9223
WS_URL = f"ws://{HOST}:{PORT}/devtools/browser/abc123"
HTTP_URL = f"http://{HOST}:{PORT}"
VERSION_URL = f"{HTTP_URL}/json/version"


class TestResolveCdpOverride:
    def test_keeps_full_devtools_websocket_url(self):
        from tools.browser_tool import _resolve_cdp_override

        assert _resolve_cdp_override(WS_URL) == WS_URL

    def test_resolves_http_discovery_endpoint_to_websocket(self):
        from tools.browser_tool import _resolve_cdp_override

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"webSocketDebuggerUrl": WS_URL}

        with patch("tools.browser_tool.requests.get", return_value=response) as mock_get:
            resolved = _resolve_cdp_override(HTTP_URL)

        assert resolved == WS_URL
        mock_get.assert_called_once_with(VERSION_URL, timeout=10)

    def test_resolves_bare_ws_hostport_to_discovery_websocket(self):
        from tools.browser_tool import _resolve_cdp_override

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"webSocketDebuggerUrl": WS_URL}

        with patch("tools.browser_tool.requests.get", return_value=response) as mock_get:
            resolved = _resolve_cdp_override(f"ws://{HOST}:{PORT}")

        assert resolved == WS_URL
        mock_get.assert_called_once_with(VERSION_URL, timeout=10)

    def test_falls_back_to_raw_url_when_discovery_fails(self):
        from tools.browser_tool import _resolve_cdp_override

        with patch("tools.browser_tool.requests.get", side_effect=RuntimeError("boom")):
            assert _resolve_cdp_override(HTTP_URL) == HTTP_URL

    def test_redacts_secret_query_params_in_success_log(self):
        from tools.browser_tool import _resolve_cdp_override

        raw = "https://cdp.example/json/version?access_token=super-secret-token-123456"
        resolved_ws = "wss://cdp.example/devtools/browser/abc?token=super-secret-token-123456"

        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"webSocketDebuggerUrl": resolved_ws}

        with patch("tools.browser_tool.requests.get", return_value=response), \
                patch("tools.browser_tool.logger.info") as mock_info:
            resolved = _resolve_cdp_override(raw)

        assert resolved == resolved_ws
        mock_info.assert_called_once()
        _, logged_raw, logged_ws = mock_info.call_args.args
        assert "super-secret-token-123456" not in logged_raw
        assert "super-secret-token-123456" not in logged_ws
        assert "access_token=***" in logged_raw
        assert "token=***" in logged_ws

    def test_redacts_secret_query_params_in_failure_log(self):
        from tools.browser_tool import _resolve_cdp_override

        raw = "https://cdp.example?access_token=super-secret-token-123456"
        secret_version_url = "https://cdp.example/json/version?access_token=super-secret-token-123456"
        secret_error = RuntimeError(
            "upstream rejected https://cdp.example/json/version?access_token=super-secret-token-123456"
        )

        with patch("tools.browser_tool.requests.get", side_effect=secret_error), \
                patch("tools.browser_tool.logger.warning") as mock_warning:
            resolved = _resolve_cdp_override(raw)

        assert resolved == raw
        mock_warning.assert_called_once()
        _, logged_raw, logged_version_url, logged_error = mock_warning.call_args.args
        assert "super-secret-token-123456" not in logged_raw
        assert "super-secret-token-123456" not in logged_version_url
        assert "super-secret-token-123456" not in logged_error
        assert "access_token=***" in logged_raw
        assert "access_token=***" in logged_version_url
        assert "access_token=***" in logged_error
        assert logged_version_url.startswith("https://cdp.example")
