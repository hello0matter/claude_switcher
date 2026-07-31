import unittest
from unittest import mock

import claude_switcher


class ClaudeSwitcherTests(unittest.TestCase):
    def test_set_global_has_no_clipboard_side_effect(self):
        app = object.__new__(claude_switcher.App)
        app.routes = [{"name": "测试路线"}]
        app._selected_idx = mock.Mock(return_value=0)
        app.sync_clawgod_var = mock.Mock()
        app.sync_clawgod_var.get.return_value = False
        app._refresh_global_status = mock.Mock()
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
        app.clipboard_clear.assert_not_called()
        app.clipboard_append.assert_not_called()
        app.status_var.set.assert_called_once_with(
            "已设为全局：测试路线（注册表 + settings.json 已更新；"
            "已运行的 Claude 不会自动切换：只改模型请用 /model，切换路线请重新启动）"
        )


if __name__ == "__main__":
    unittest.main()
