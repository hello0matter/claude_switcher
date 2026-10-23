import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import codex_panel
import prompt_probe


class PromptProbeTests(unittest.TestCase):
    def test_non_subdomain_host_drops_only_the_left_label(self):
        self.assertEqual(prompt_probe.non_subdomain_host("https://api.xiaomimimo.com/v1"), "xiaomimimo.com")
        self.assertEqual(prompt_probe.non_subdomain_host("https://okai.la"), "okai.la")
        self.assertEqual(prompt_probe.non_subdomain_host("https://api.tokenbits.net/v1"), "tokenbits.net")
        self.assertEqual(prompt_probe.non_subdomain_host(""), "nohost")

    def test_filename_contains_time_host_model_effort_and_wire(self):
        route = {
            "base_url": "https://api.xiaomimimo.com/v1",
            "model": "mimo-v2.6-pro",
            "reasoning_effort": "medium",
            "wire_api": "responses",
        }
        name = prompt_probe.prompt_filename(route, datetime(2026, 10, 23, 15, 30, 45))
        self.assertEqual(
            name,
            "20261023-153045_xiaomimimo.com_mimo-v2.6-pro_medium_responses.html",
        )

    def test_prepare_route_form_keeps_api_address_and_selected_suffix(self):
        prepared = prompt_probe.prepare_route_form(
            {
                "base_url": "https://api.example.com/v1/chat/completions/",
                "wire_api": "chat",
            }
        )
        self.assertEqual(prepared["base_url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual(prepared["wire_api"], "/chat/completions")

    def test_empty_suffix_appends_nothing_and_does_not_strip_address(self):
        self.assertEqual(
            prompt_probe.join_api_url("https://api.example/v1/responses", ""),
            "https://api.example/v1/responses",
        )
        self.assertEqual(
            prompt_probe.join_api_url("https://api.example/v1", "/chat/completions"),
            "https://api.example/v1/chat/completions",
        )
        self.assertEqual(prompt_probe.normalize_wire_suffix("（不追加）", default="/responses"), "")

    def test_render_prompt_fills_path_and_default_forbids_publish(self):
        route = {"name": "xiaomi", "model": "mimo", "base_url": "https://api.xiaomimimo.com/v1"}
        text = prompt_probe.render_prompt(prompt_probe.DEFAULT_PROMPT, route, Path(r"D:\tmp\out.html"))
        self.assertIn(r"D:\tmp\out.html", text)
        self.assertFalse(prompt_probe.prompt_mentions_git_publish(text))
        self.assertTrue(prompt_probe.prompt_mentions_git_publish("请提交并推送这个文件"))

    def test_missing_placeholder_still_appends_output_path(self):
        text = prompt_probe.render_prompt("只写动画", {"model": "m"}, Path("out.html"))
        self.assertIn("out.html", text)

    def test_config_override_forces_responses_and_does_not_use_chat(self):
        args = prompt_probe.config_override_args(
            {
                "provider_id": "mc",
                "name": "xiaomi",
                "base_url": "https://api.example/v1/responses",
                "api_key": "secret",
                "reasoning_effort": "medium",
                "wire_api": "chat",
            }
        )
        joined = " ".join(args)
        self.assertNotIn("wire_api=", joined)
        self.assertIn('model_providers.mc.base_url="https://api.example/v1/responses"', joined)
        self.assertIn("secret", joined)

    def test_unsafe_provider_id_is_rejected_for_batch(self):
        self.assertTrue(prompt_probe.provider_id_problem({"provider_id": "mc 5.5"}))
        self.assertEqual(prompt_probe.provider_id_problem({"provider_id": "mc"}), "")
    def test_prompt_test_disables_web_search_per_process(self):
        args = prompt_probe.config_override_args(
            {
                "provider_id": "mc",
                "base_url": "https://api.example/v1",
                "api_key": "secret",
                "wire_api": "/responses",
            }
        )
        self.assertIn('web_search="disabled"', args)

    def test_prompt_test_rejects_non_responses_wire_suffixes(self):
        self.assertEqual(prompt_probe.prompt_wire_problem({"wire_api": "/responses"}), "")
        self.assertEqual(prompt_probe.prompt_wire_problem({"wire_api": ""}), "")
        self.assertIn("/completions", prompt_probe.prompt_wire_problem({"wire_api": "/completions"}))
        self.assertIn(
            "/chat/completions",
            prompt_probe.prompt_wire_problem({"wire_api": "/chat/completions"}),
        )


    def test_launch_command_can_carry_prompt_without_changing_plain_launch(self):
        with mock.patch.object(codex_panel, "_powershell_console", return_value="pwsh.exe"):
            plain = codex_panel._codex_console_command("codex")
            prompted = codex_panel._codex_console_command(
                "codex",
                {"provider_id": "mc", "model": "mimo"},
                prompt="write html",
                workdir=r"D:\tmp\out",
            )
        self.assertEqual(plain, ["pwsh.exe", "-NoExit", "-Command", "& 'codex' '--yolo'"])
        self.assertIn("write html", prompted[-1])
        self.assertIn("-C", prompted[-1])
        self.assertIn("D:\\tmp\\out", prompted[-1])

    def test_exec_arguments_do_not_rewrite_config_and_skip_git(self):
        args = codex_panel._codex_exec_arguments(
            "codex",
            {
                "provider_id": "mc",
                "model": "mimo",
                "base_url": "https://api.example/v1",
                "api_key": "secret",
            },
            "write html",
            r"D:\tmp\out",
        )
        self.assertEqual(args[1], "exec")
        self.assertIn("--skip-git-repo-check", args)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", args)
        self.assertNotIn("--yolo", args)
        self.assertEqual(args[-1], "write html")

    def test_windows_prompt_test_uses_powershell_shim_without_holding_window(self):
        with mock.patch.object(codex_panel, "_powershell_console", return_value="powershell.exe"), mock.patch.object(
            codex_panel, "os"
        ) as fake_os:
            fake_os.name = "nt"
            fake_os.environ = {}
            command = codex_panel.prompt_test_command(
                "codex",
                {"provider_id": "mc", "model": "mimo", "base_url": "https://api.example/v1"},
                "write html",
                r"D:\tmp\out",
                True,
            )
        self.assertEqual(command[0], "powershell.exe")
        self.assertNotIn("-NoExit", command)
        self.assertIn("exec", command[-1])
        self.assertIn("write html", command[-1])

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "prompt.json"
            with mock.patch.object(prompt_probe, "PROMPT_SETTINGS_FILE", target):
                saved = prompt_probe.save_prompt_settings(
                    {"output_dir": r"D:\tmp\tmp\大模型智力评测", "prompt": "hello {output_path}", "hidden": False}
                )
                loaded = prompt_probe.load_prompt_settings()
        self.assertEqual(saved, loaded)
        self.assertFalse(loaded["hidden"])
        self.assertIn("output_path", loaded["prompt"])


if __name__ == "__main__":
    unittest.main()
