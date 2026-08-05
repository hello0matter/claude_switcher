import unittest
import json
from unittest import mock

import claude_switcher


class ClaudeSwitcherTests(unittest.TestCase):
    def test_active_claude_route_uses_endpoint_and_model(self):
        app = object.__new__(claude_switcher.App)
        app.routes = [
            {
                "name": "route-a",
                "base_url": "https://a.example/v1",
                "model": "claude-a",
            },
            {
                "name": "route-b",
                "base_url": "https://b.example/v1",
                "model": "claude-b",
            },
        ]
        with mock.patch.object(
            claude_switcher,
            "load_settings",
            return_value={
                "model": "claude-b",
                "env": {"ANTHROPIC_BASE_URL": "https://b.example/v1"},
            },
        ), mock.patch.object(
            claude_switcher.os.path, "exists", return_value=False
        ):
            active = app._active_route_index()

        self.assertEqual(active, 1)

    def test_set_global_has_no_clipboard_side_effect(self):
        app = object.__new__(claude_switcher.App)
        app.routes = [{"name": "测试路线"}]
        app._selected_idx = mock.Mock(return_value=0)
        app.sync_clawgod_var = mock.Mock()
        app.sync_clawgod_var.get.return_value = False
        app._refresh_global_status = mock.Mock()
        app._refresh_list = mock.Mock()
        app.status_var = mock.Mock()
        app.clipboard_clear = mock.Mock()
        app.clipboard_append = mock.Mock()

        with mock.patch.object(claude_switcher, "apply_global") as apply_global, \
                mock.patch.object(claude_switcher, "sync_settings") as sync_settings, \
                mock.patch.object(claude_switcher, "sync_oauth_identity") as sync_oauth, \
                mock.patch.object(claude_switcher, "sync_clawgod_warlord") as sync_clawgod:
            claude_switcher.App._set_global(app)

        apply_global.assert_called_once_with(app.routes[0])
        sync_settings.assert_called_once_with(app.routes[0])
        sync_oauth.assert_called_once_with(app.routes[0])
        sync_clawgod.assert_not_called()
        app._refresh_global_status.assert_called_once_with()
        app._refresh_list.assert_called_once_with(0)
        app.clipboard_clear.assert_not_called()
        app.clipboard_append.assert_not_called()
        app.status_var.set.assert_called_once_with(
            "已设为全局：测试路线（注册表 + settings.json 已更新；"
            "已运行的 Claude 不会自动切换：只改模型请用 /model，切换路线请重新启动）"
        )

    def test_claude_route_integrity_check_passes_streaming_canary(self):
        response = mock.MagicMock()
        response.status = 200
        response.geturl.return_value = "https://api.example/v1/messages"
        response.read.return_value = (
            b'event: content_block_delta\n'
            b'data: {"type":"content_block_delta","delta":{"type":"text_delta",'
            b'"text":"CLAUDE_ROUTE_CHECK_OK_abc123"}}\n\n'
            b'data: {"type":"message_stop"}\n\n'
        )
        context = mock.MagicMock()
        context.__enter__.return_value = response
        route = {
            "base_url": "https://api.example/v1",
            "api_key": "test-key",
            "auth_var": "ANTHROPIC_API_KEY",
            "model": "claude-test",
        }
        with mock.patch.object(
            claude_switcher.secrets, "token_hex", return_value="abc123"
        ), mock.patch.object(
            claude_switcher.urllib.request, "urlopen", return_value=context
        ) as urlopen:
            result = claude_switcher.check_claude_route_integrity(route)

        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["summary"], "未发现明显投毒迹象")
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertTrue(payload["stream"])
        self.assertEqual(payload["model"], "claude-test")
        self.assertIn("PRIVATE_CLAUDE_ROUTE_CANARY_abc123", payload["system"])
        self.assertEqual(request.headers["X-api-key"], "test-key")

    def test_claude_route_anomaly_distinguishes_failed_probe(self):
        with mock.patch.object(
            claude_switcher,
            "check_claude_route_integrity",
            return_value={
                "verdict": "inconclusive",
                "summary": "检测请求失败，无法判断是否投毒",
                "details": ["HTTP 502: upstream error"],
                "latency_ms": "1200",
            },
        ):
            result = claude_switcher.check_claude_route_anomaly({"model": "claude-test"})

        self.assertEqual(result["verdict"], "anomaly")
        self.assertEqual(result["summary"], "检测到路线异常或请求中断（不等于已经确认投毒）")


if __name__ == "__main__":
    unittest.main()
