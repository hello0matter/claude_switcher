"""Cross-platform helpers for launching a command in a new terminal window.

Windows keeps the historical behavior (cmd /k or PowerShell + CREATE_NEW_CONSOLE).
Linux/BSD picks a common terminal emulator and keeps it open after the command exits.
"""

import os
import shlex
import shutil

# (program, exec separator). None means the terminal accepts the command directly.
_TERMINAL_CANDIDATES = (
    ("x-terminal-emulator", "-e"),  # Debian/Kali wrapper
    ("gnome-terminal", "--"),
    ("konsole", "-e"),
    ("xfce4-terminal", "-e"),
    ("kitty", None),
    ("alacritty", "-e"),
    ("foot", None),
    ("xterm", "-e"),
)

_DASH_DASH_TERMINALS = {"gnome-terminal", "mate-terminal"}


def is_windows():
    return os.name == "nt"


def _hold_shell_line(command):
    shell_line = shlex.join(command)
    return f"{shell_line}; exec bash"


_SEPARATORS = dict(_TERMINAL_CANDIDATES)


def _separator_for(program):
    base = os.path.basename(program)
    if base in _DASH_DASH_TERMINALS:
        return "--"
    return _SEPARATORS.get(base, "-e")


def _terminal_argv(program, hold_line, separator=None):
    if separator is None:
        separator = _separator_for(program)
    prefix = [program]
    if separator is not None:
        prefix.append(separator)
    return prefix + ["bash", "-lc", hold_line]


def _configured_terminal(hold_line):
    raw = os.environ.get("CLAUDE_SWITCHER_TERMINAL") or os.environ.get("TERMINAL")
    if not raw:
        return None
    parts = shlex.split(raw)
    if not parts:
        return None
    program = parts[0]
    resolved = shutil.which(program) or (program if os.path.isfile(program) else None)
    if resolved is None:
        return None
    # Only a single terminal command is supported; extra args are ignored.
    return _terminal_argv(resolved, hold_line)


def _termux_argv(hold_line):
    return ["bash", "-lc", hold_line]


def new_terminal_argv(command):
    """Build argv that runs *command* in a new terminal window (non-Windows)."""
    hold_line = _hold_shell_line(command)

    # Android/Termux has no X terminal registry; reuse the launching shell.
    if os.environ.get("TERMUX_VERSION") or os.path.exists("/data/data/com.termux"):
        return _termux_argv(hold_line)

    configured = _configured_terminal(hold_line)
    if configured is not None:
        return configured

    for program, separator in _TERMINAL_CANDIDATES:
        path = shutil.which(program)
        if path:
            return _terminal_argv(path, hold_line, separator)

    raise FileNotFoundError(
        "未找到可用的终端模拟器\n"
        "请安装 x-terminal-emulator/gnome-terminal/kitty 之一，"
        "或设置环境变量 CLAUDE_SWITCHER_TERMINAL 指向你的终端命令"
    )
