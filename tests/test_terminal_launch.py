import os
import unittest
from unittest import mock

import terminal_launch


class NewTerminalArgvTests(unittest.TestCase):
    def test_uses_debian_terminal_wrapper(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_SWITCHER_TERMINAL", None)
            os.environ.pop("TERMINAL", None)
            with mock.patch.object(terminal_launch.shutil, "which", side_effect=lambda p: f"/usr/bin/{p}" if p == "x-terminal-emulator" else None):
                argv = terminal_launch.new_terminal_argv(["claude"])
        self.assertEqual(argv[0], "/usr/bin/x-terminal-emulator")
        self.assertEqual(argv[1:2], ["-e"])
        self.assertEqual(argv[2:4], ["bash", "-lc"])
        self.assertIn("claude; exec bash", argv[4])

    def test_gnome_terminal_uses_double_dash(self):
        with mock.patch.dict(os.environ, {"CLAUDE_SWITCHER_TERMINAL": "gnome-terminal"}):
            with mock.patch.object(terminal_launch.shutil, "which", return_value="/usr/bin/gnome-terminal"):
                argv = terminal_launch.new_terminal_argv(["codex", "--yolo"])
        self.assertEqual(argv, ["/usr/bin/gnome-terminal", "--", "bash", "-lc", "codex --yolo; exec bash"])

    def test_termux_runs_in_current_shell(self):
        with mock.patch.dict(os.environ, {"TERMUX_VERSION": "1"}):
            argv = terminal_launch.new_terminal_argv(["claude"])
        self.assertEqual(argv, ["bash", "-lc", "claude; exec bash"])

    def test_missing_terminal_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(terminal_launch.shutil, "which", return_value=None):
                with self.assertRaises(FileNotFoundError):
                    terminal_launch.new_terminal_argv(["claude"])


if __name__ == "__main__":
    unittest.main()
