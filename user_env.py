"""Cross-platform user-level environment variable persistence.

Windows keeps the original HKCU\\Environment registry behavior (plus the
WM_SETTINGCHANGE broadcast). Linux/macOS stores a machine-readable state file
and mirrors the values into managed blocks in ~/.bashrc and ~/.zshenv so new
terminals inherit them, and also updates the current process environment.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

_BEGIN = "# >>> claude_switcher environment >>>"
_END = "# <<< claude_switcher environment <<<"
_RC_FILES = (".bashrc", ".zshenv")


def _is_windows() -> bool:
    return os.name == "nt"


def _state_path() -> Path:
    override = os.environ.get("CLAUDE_SWITCHER_ENV_FILE")
    if override:
        return Path(override)
    return Path.home() / ".claude_switcher_env.json"


def _load_state() -> dict:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        pass
    return {}


def _save_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_block(state: dict) -> str:
    lines = [_BEGIN]
    lines.extend(f"export {key}={shlex.quote(value)}" for key, value in sorted(state.items()))
    lines.append(_END)
    return "\n".join(lines) + "\n"


def _sync_rc_files(state: dict) -> None:
    block = _render_block(state)
    pattern = re.compile(re.escape(_BEGIN) + r".*?" + re.escape(_END) + r"\n?", re.DOTALL)
    for name in _RC_FILES:
        path = Path.home() / name
        try:
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            if pattern.search(text):
                text = pattern.sub(lambda _m: block, text)
            else:
                text = text.rstrip("\n") + ("\n\n" if text else "") + block
            path.write_text(text, encoding="utf-8")
        except OSError:
            # A missing or unwritable rc file must not break switching routes.
            continue


def _windows_get(name):
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except FileNotFoundError:
        return None


def _windows_broadcast() -> None:
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    import ctypes

    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 2, 1000, None
    )


def get_value(name):
    if _is_windows():
        return _windows_get(name)
    return _load_state().get(name)


def set_value(name, value):
    if _is_windows():
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, value)
        _windows_broadcast()
        return
    state = _load_state()
    state[name] = str(value)
    _save_state(state)
    _sync_rc_files(state)
    os.environ[name] = str(value)


def delete_value(name):
    if _is_windows():
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, name)
            _windows_broadcast()
        except FileNotFoundError:
            pass
        return
    state = _load_state()
    state.pop(name, None)
    _save_state(state)
    _sync_rc_files(state)
    os.environ.pop(name, None)
