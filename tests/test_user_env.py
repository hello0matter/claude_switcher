import os
import unittest
from unittest import mock
from pathlib import Path

import user_env


class UserEnvTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        patcher_env = mock.patch.dict(os.environ, {"CLAUDE_SWITCHER_ENV_FILE": str(self.home / "env.json")}, clear=False)
        patcher_home = mock.patch.object(Path, "home", staticmethod(lambda: self.home))
        patcher_nt = mock.patch.object(user_env, "_is_windows", return_value=False)
        for patcher in (patcher_env, patcher_home, patcher_nt):
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_set_get_delete_roundtrip(self):
        user_env.set_value("ANTHROPIC_BASE_URL", "https://example.com/v1")
        self.assertEqual(user_env.get_value("ANTHROPIC_BASE_URL"), "https://example.com/v1")
        self.assertEqual(os.environ["ANTHROPIC_BASE_URL"], "https://example.com/v1")

        block = (self.home / ".bashrc").read_text(encoding="utf-8")
        self.assertIn("export ANTHROPIC_BASE_URL=", block)
        self.assertIn(user_env._BEGIN, block)
        zsh = (self.home / ".zshenv").read_text(encoding="utf-8")
        self.assertIn("export ANTHROPIC_BASE_URL=", zsh)

        user_env.delete_value("ANTHROPIC_BASE_URL")
        self.assertIsNone(user_env.get_value("ANTHROPIC_BASE_URL"))
        self.assertNotIn("ANTHROPIC_BASE_URL", os.environ)
        self.assertNotIn("export ANTHROPIC_BASE_URL", (self.home / ".bashrc").read_text(encoding="utf-8"))

    def test_values_with_spaces_are_quoted(self):
        user_env.set_value("ANTHROPIC_MODEL", "model name")
        line = next(
            line for line in (self.home / ".bashrc").read_text(encoding="utf-8").splitlines()
            if line.startswith("export ANTHROPIC_MODEL=")
        )
        self.assertIn("model name", line)
        # shlex.quote wraps anything containing spaces.
        self.assertTrue(line.split("=", 1)[1].startswith("'"))

    def test_delete_missing_is_noop(self):
        user_env.delete_value("NEVER_SET")
        self.assertIsNone(user_env.get_value("NEVER_SET"))


if __name__ == "__main__":
    unittest.main()
