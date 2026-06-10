import tkinter as tk
from tkinter import messagebox
import json
import os
import subprocess
import winreg
import ctypes

CONFIG_FILE   = os.path.expanduser("~/.cc_routes.json")
SETTINGS_FILE = os.path.expanduser("~/.claude/settings.json")

DEFAULT_ROUTES = [
    {
        "name": "官方 Anthropic",
        "base_url": "",
        "api_key": "",
        "model": "",
        "note": "使用系统 ANTHROPIC_API_KEY，不覆盖任何变量",
    },
    {
        "name": "LiteLLM 本地代理 (智谱)",
        "base_url": "http://localhost:4000",
        "api_key": "sk-any",
        "model": "claude-sonnet-4-8",
        "note": "GLM via LiteLLM proxy",
    },
]


# ── 系统环境变量读写（用户级）────────────────────────────────────────────────

REG_PATH = r"Environment"  # HKCU\Environment

def _get_user_env(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as k:
            val, _ = winreg.QueryValueEx(k, name)
            return val
    except FileNotFoundError:
        return None

def _set_user_env(name, value):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_EXPAND_SZ, value)
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    ctypes.windll.user32.SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 2, 1000, None
    )

def _del_user_env(name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 2, 1000, None
        )
    except FileNotFoundError:
        pass

def get_global_route():
    return _get_user_env("ANTHROPIC_BASE_URL")

def apply_global(route):
    if route.get("base_url"):
        _set_user_env("ANTHROPIC_BASE_URL", route["base_url"])
    else:
        _del_user_env("ANTHROPIC_BASE_URL")
    if route.get("api_key"):
        _set_user_env("ANTHROPIC_API_KEY", route["api_key"])
    if route.get("model"):
        _set_user_env("ANTHROPIC_MODEL", route["model"])
    else:
        _del_user_env("ANTHROPIC_MODEL")

def clear_global():
    _del_user_env("ANTHROPIC_BASE_URL")
    _del_user_env("ANTHROPIC_MODEL")


# ── settings.json 读写 ────────────────────────────────────────────────────────

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(settings):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def sync_settings(route):
    """将路线的 base_url / api_key / model 同步写入 ~/.claude/settings.json"""
    settings = load_settings()
    env = settings.setdefault("env", {})

    if route.get("base_url"):
        env["ANTHROPIC_BASE_URL"] = route["base_url"]
    else:
        env.pop("ANTHROPIC_BASE_URL", None)

    if route.get("api_key"):
        env["ANTHROPIC_AUTH_TOKEN"] = route["api_key"]

    if route.get("model"):
        settings["model"] = route["model"]

    save_settings(settings)

def read_settings_model():
    return load_settings().get("model", "")


# ── 路线持久化 ────────────────────────────────────────────────────────────────

def load_routes():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                routes = json.load(f)
            for r in routes:
                r.setdefault("model", "")
            return routes
        except Exception:
            pass
    return [r.copy() for r in DEFAULT_ROUTES]

def save_routes(routes):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(routes, f, ensure_ascii=False, indent=2)


# ── 编辑/新增对话框 ───────────────────────────────────────────────────────────

class RouteEditor(tk.Toplevel):
    def __init__(self, parent, route=None, title="添加路线"):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None

        route = route or {"name": "", "base_url": "", "api_key": "", "model": "", "note": ""}

        fields = [
            ("名称 *",               "name",     False),
            ("ANTHROPIC_BASE_URL",   "base_url", False),
            ("ANTHROPIC_AUTH_TOKEN", "api_key",  True),
            ("model（留空不覆盖）",   "model",    False),
            ("备注",                 "note",     False),
        ]

        self.vars = {}
        self._key_entry = None

        for i, (label, key, secret) in enumerate(fields):
            tk.Label(self, text=label, anchor="w", width=24).grid(
                row=i, column=0, padx=(12, 4), pady=6, sticky="w"
            )
            var = tk.StringVar(value=route.get(key, ""))
            entry = tk.Entry(self, textvariable=var, width=42)
            if secret:
                entry.config(show="*")
                self._key_entry = entry
            entry.grid(row=i, column=1, padx=(4, 4), pady=6)
            self.vars[key] = var

        self._show_key = False
        tk.Button(self, text="👁", width=3, command=self._toggle_key).grid(
            row=2, column=2, padx=(0, 8)
        )

        btn_frame = tk.Frame(self)
        btn_frame.grid(row=len(fields), column=0, columnspan=3, pady=(8, 12))
        tk.Button(btn_frame, text="保存", command=self._save, width=10).pack(side="left", padx=6)
        tk.Button(btn_frame, text="取消", command=self.destroy, width=10).pack(side="left", padx=6)

        self.grab_set()
        self.wait_window()

    def _toggle_key(self):
        self._show_key = not self._show_key
        self._key_entry.config(show="" if self._show_key else "*")

    def _save(self):
        name = self.vars["name"].get().strip()
        if not name:
            messagebox.showwarning("提示", "名称不能为空", parent=self)
            return
        self.result = {k: v.get().strip() for k, v in self.vars.items()}
        self.destroy()


# ── 主窗口 ────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Claude Route Switcher")
        self.geometry("720x440")
        self.minsize(560, 360)

        self.routes = load_routes()
        self._build_ui()
        self._refresh_list(0)
        self._refresh_global_status()

    def _build_ui(self):
        # ── 顶部全局状态栏 ──
        top = tk.Frame(self, bg="#f0f0f0", pady=4)
        top.pack(fill="x", padx=10, pady=(8, 0))

        tk.Label(top, text="全局路线：", bg="#f0f0f0", font=("", 9)).pack(side="left")
        self.global_label = tk.Label(top, text="", bg="#f0f0f0", font=("", 9, "bold"), fg="#1565C0")
        self.global_label.pack(side="left")

        tk.Label(top, text="  model：", bg="#f0f0f0", font=("", 9)).pack(side="left")
        self.model_label = tk.Label(top, text="", bg="#f0f0f0", font=("", 9, "bold"), fg="#6A1B9A")
        self.model_label.pack(side="left")

        tk.Button(
            top, text="清除全局（恢复官方）",
            command=self._clear_global,
            relief="flat", bg="#e0e0e0", font=("", 8), cursor="hand2",
        ).pack(side="right", padx=4)

        # ── 主体：左列表 + 右详情 ──
        body = tk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        # 左侧
        left = tk.Frame(body)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        tk.Label(left, text="路线列表", font=("", 10, "bold")).pack(anchor="w")

        list_frame = tk.Frame(left)
        list_frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(list_frame, orient="vertical")
        self.listbox = tk.Listbox(
            list_frame, selectmode="single", font=("Consolas", 10),
            yscrollcommand=sb.set, activestyle="dotbox",
        )
        sb.config(command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)

        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self.listbox.bind("<Double-Button-1>", lambda e: self._launch())

        list_btns = tk.Frame(left)
        list_btns.pack(fill="x", pady=(4, 0))
        for text, cmd in [("➕", self._add), ("✏️", self._edit), ("🗑", self._delete),
                          ("⬆", self._move_up), ("⬇", self._move_down)]:
            tk.Button(list_btns, text=text, width=4, command=cmd).pack(side="left", padx=2)

        # 右侧
        right = tk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        tk.Label(right, text="详情", font=("", 10, "bold")).pack(anchor="w")

        detail = tk.LabelFrame(right, text="", padx=8, pady=6)
        detail.pack(fill="both", expand=True)

        self.detail_vars = {}
        for label, key in [("名称", "name"), ("BASE_URL", "base_url"),
                            ("AUTH_TOKEN", "api_key"), ("model", "model"), ("备注", "note")]:
            row = tk.Frame(detail)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label + ":", width=10, anchor="w", fg="#666").pack(side="left")
            var = tk.StringVar()
            tk.Label(row, textvariable=var, anchor="w", wraplength=210, justify="left").pack(
                side="left", fill="x", expand=True
            )
            self.detail_vars[key] = var

        btn_area = tk.Frame(right)
        btn_area.pack(fill="x", pady=(10, 0))

        tk.Button(
            btn_area, text="🌐  设为全局",
            command=self._set_global,
            bg="#1565C0", fg="white", font=("", 10, "bold"),
            relief="flat", padx=8, pady=5, cursor="hand2",
        ).pack(fill="x", pady=(0, 4))

        tk.Button(
            btn_area, text="🚀  仅此次启动",
            command=self._launch,
            bg="#4CAF50", fg="white", font=("", 10, "bold"),
            relief="flat", padx=8, pady=5, cursor="hand2",
        ).pack(fill="x")

        self.status_var = tk.StringVar(value="选择路线后操作")
        tk.Label(right, textvariable=self.status_var, fg="#888", font=("", 8)).pack(
            anchor="w", pady=(4, 0)
        )

    # ── 全局状态 ──────────────────────────────────────────────────────────────

    def _refresh_global_status(self):
        val = get_global_route()
        if val:
            name = next((r["name"] for r in self.routes if r.get("base_url") == val), val)
            self.global_label.config(text=name, fg="#1565C0")
        else:
            self.global_label.config(text="官方 Anthropic（未设代理）", fg="#555")

        model = read_settings_model() or (_get_user_env("ANTHROPIC_MODEL") or "")
        self.model_label.config(text=model if model else "（未设）")

    def _set_global(self):
        idx = self._selected_idx()
        if idx is None:
            messagebox.showwarning("提示", "请先选择一条路线")
            return
        r = self.routes[idx]
        apply_global(r)
        sync_settings(r)
        self._refresh_global_status()
        self.status_var.set(f"已设为全局：{r['name']}（注册表 ANTHROPIC_MODEL + settings.json 已更新）")

    def _clear_global(self):
        clear_global()
        self._refresh_global_status()
        self.status_var.set("已清除全局代理，恢复官方")

    # ── 列表操作 ──────────────────────────────────────────────────────────────

    def _refresh_list(self, select_idx=None):
        self.listbox.delete(0, "end")
        for r in self.routes:
            label = r["name"]
            if r.get("model"):
                label += f"  [{r['model']}]"
            self.listbox.insert("end", label)
        if select_idx is not None and self.routes:
            idx = max(0, min(select_idx, len(self.routes) - 1))
            self.listbox.selection_set(idx)
            self.listbox.see(idx)
            self._update_detail(idx)

    def _selected_idx(self):
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _on_select(self, event=None):
        idx = self._selected_idx()
        if idx is not None:
            self._update_detail(idx)

    def _update_detail(self, idx):
        r = self.routes[idx]
        self.detail_vars["name"].set(r.get("name", ""))
        self.detail_vars["base_url"].set(r.get("base_url", "") or "(系统默认，不覆盖)")
        key = r.get("api_key", "")
        masked = (key[:4] + "****" + key[-4:] if len(key) > 8 else "****") if key else "(系统默认，不覆盖)"
        self.detail_vars["api_key"].set(masked)
        self.detail_vars["model"].set(r.get("model", "") or "(留空，不覆盖)")
        self.detail_vars["note"].set(r.get("note", ""))

    def _add(self):
        editor = RouteEditor(self, title="添加路线")
        if editor.result:
            self.routes.append(editor.result)
            save_routes(self.routes)
            self._refresh_list(len(self.routes) - 1)

    def _edit(self):
        idx = self._selected_idx()
        if idx is None:
            return
        editor = RouteEditor(self, route=self.routes[idx], title="编辑路线")
        if editor.result:
            self.routes[idx] = editor.result
            save_routes(self.routes)
            self._refresh_list(idx)

    def _delete(self):
        idx = self._selected_idx()
        if idx is None:
            return
        name = self.routes[idx]["name"]
        if messagebox.askyesno("确认删除", f"删除路线「{name}」？"):
            self.routes.pop(idx)
            save_routes(self.routes)
            self._refresh_list(min(idx, len(self.routes) - 1) if self.routes else None)

    def _move_up(self):
        idx = self._selected_idx()
        if idx is None or idx == 0:
            return
        self.routes[idx - 1], self.routes[idx] = self.routes[idx], self.routes[idx - 1]
        save_routes(self.routes)
        self._refresh_list(idx - 1)

    def _move_down(self):
        idx = self._selected_idx()
        if idx is None or idx >= len(self.routes) - 1:
            return
        self.routes[idx + 1], self.routes[idx] = self.routes[idx], self.routes[idx + 1]
        save_routes(self.routes)
        self._refresh_list(idx + 1)

    # ── 仅此次启动 ────────────────────────────────────────────────────────────

    def _launch(self):
        idx = self._selected_idx()
        if idx is None:
            messagebox.showwarning("提示", "请先选择一条路线")
            return
        r = self.routes[idx]
        # model 既写入 settings.json，也通过子进程环境变量 ANTHROPIC_MODEL 传递
        sync_settings(r)
        self._refresh_global_status()
        env = os.environ.copy()
        if r.get("base_url"):
            env["ANTHROPIC_BASE_URL"] = r["base_url"]
        else:
            env.pop("ANTHROPIC_BASE_URL", None)
        if r.get("api_key"):
            env["ANTHROPIC_API_KEY"]    = r["api_key"]
            env["ANTHROPIC_AUTH_TOKEN"] = r["api_key"]
        if r.get("model"):
            env["ANTHROPIC_MODEL"] = r["model"]
        else:
            env.pop("ANTHROPIC_MODEL", None)
        try:
            subprocess.Popen(
                ["cmd", "/k", "claude"],
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            self.status_var.set(f"已启动（settings.json 已同步）：{r['name']}")
        except FileNotFoundError:
            messagebox.showerror("错误", "找不到 claude 命令\n请确认 Claude Code 已安装并在 PATH 中")


if __name__ == "__main__":
    app = App()
    app.mainloop()
