"""Network transport used only by this switcher's model and route probes."""

import functools
import http.client
import json
import os
import socket
import tempfile
import tkinter as tk
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk


NETWORK_CONFIG_FILE = Path.home() / ".claude_switcher_network.json"
NETWORK_MODES = {
    "direct": "直连",
    "http": "HTTP 代理",
    "socks5h": "SOCKS5（远程 DNS）",
}
DEFAULT_NETWORK_CONFIG = {
    "mode": "direct",
    "host": "127.0.0.1",
    "port": 7891,
}


def load_network_config():
    config = dict(DEFAULT_NETWORK_CONFIG)
    if NETWORK_CONFIG_FILE.exists():
        try:
            stored = json.loads(NETWORK_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                config.update(stored)
        except (OSError, TypeError, ValueError):
            pass
    mode = str(config.get("mode") or "direct")
    config["mode"] = mode if mode in NETWORK_MODES else "direct"
    config["host"] = str(config.get("host") or "127.0.0.1").strip()
    try:
        config["port"] = int(config.get("port") or 7891)
    except (TypeError, ValueError):
        config["port"] = 7891
    return config


def save_network_config(config):
    normalized = {
        "mode": str(config.get("mode") or "direct"),
        "host": str(config.get("host") or "127.0.0.1").strip(),
        "port": int(config.get("port") or 7891),
    }
    NETWORK_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=NETWORK_CONFIG_FILE.name + ".", dir=NETWORK_CONFIG_FILE.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(normalized, stream, ensure_ascii=False, indent=2)
        Path(temp_name).replace(NETWORK_CONFIG_FILE)
    finally:
        temp = Path(temp_name)
        if temp.exists():
            temp.unlink()
    return normalized


def network_config_display(config=None):
    config = config or load_network_config()
    mode = config.get("mode", "direct")
    if mode == "direct":
        return "直连"
    return f"{NETWORK_MODES.get(mode, mode)} {config['host']}:{config['port']}"


class _SocksHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, proxy_options=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _socks_connection_factory(proxy_options)


class _SocksHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, proxy_options=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _socks_connection_factory(proxy_options)


def _socks_connection_factory(proxy_options):
    try:
        import socks
    except ImportError as exc:
        raise RuntimeError("缺少 PySocks；请运行 python -m pip install PySocks") from exc
    return functools.partial(
        socks.create_connection,
        proxy_type=socks.SOCKS5,
        proxy_addr=proxy_options["host"],
        proxy_port=proxy_options["port"],
        proxy_rdns=True,
    )


class _SocksProxyHandler(urllib.request.HTTPHandler, urllib.request.HTTPSHandler):
    def __init__(self, config):
        super().__init__()
        self.config = config

    def http_open(self, request):
        connection = functools.partial(
            _SocksHTTPConnection, proxy_options=self.config
        )
        return self.do_open(connection, request)

    def https_open(self, request):
        connection = functools.partial(
            _SocksHTTPSConnection, proxy_options=self.config
        )
        return self.do_open(connection, request)


def build_app_opener(config=None):
    config = config or load_network_config()
    mode = config.get("mode", "direct")
    if mode == "http":
        proxy_url = f"http://{config['host']}:{config['port']}"
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        )
    if mode == "socks5h":
        return urllib.request.build_opener(_SocksProxyHandler(config))
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def open_app_request(request, timeout=45):
    """Open a request through the switcher's private transport settings."""
    return build_app_opener().open(request, timeout=timeout)


def describe_network_error(exc):
    text = str(exc)
    config = load_network_config()
    if "10061" in text or "connection refused" in text.lower():
        if config.get("mode") != "direct":
            return (
                f"无法连接本软件代理 {config['host']}:{config['port']}（WinError 10061）。"
                "请启动 Clash/代理程序，或在右上角“全局设置”中改为直连。"
            )
    if "11001" in text or "11002" in text or "getaddrinfo failed" in text:
        if config.get("mode") == "direct":
            return (
                "本机 DNS 无法解析目标域名。可在右上角“全局设置”中启用 "
                "SOCKS5（远程 DNS）来绕过本地 DNS。"
            )
    return text


class NetworkSettingsDialog(tk.Toplevel):
    def __init__(self, parent, on_saved=None):
        super().__init__(parent)
        self.title("全局设置 - 本软件网络")
        self.resizable(False, False)
        self.on_saved = on_saved
        config = load_network_config()
        self.mode_var = tk.StringVar(value=NETWORK_MODES[config["mode"]])
        self.host_var = tk.StringVar(value=config["host"])
        self.port_var = tk.StringVar(value=str(config["port"]))
        self.status_var = tk.StringVar()

        tk.Label(
            self,
            text="该代理只用于本软件的模型测试和路线检测，不修改 Codex、Claude或系统代理。",
            fg="#1565C0",
            font=("", 9, "bold"),
            wraplength=480,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, padx=14, pady=(12, 10), sticky="w")
        tk.Label(self, text="网络模式", width=13, anchor="w").grid(
            row=1, column=0, padx=(14, 4), pady=6, sticky="w"
        )
        ttk.Combobox(
            self,
            textvariable=self.mode_var,
            values=tuple(NETWORK_MODES.values()),
            state="readonly",
            width=30,
        ).grid(row=1, column=1, padx=(0, 14), pady=6, sticky="ew")
        tk.Label(self, text="代理地址", width=13, anchor="w").grid(
            row=2, column=0, padx=(14, 4), pady=6, sticky="w"
        )
        tk.Entry(self, textvariable=self.host_var, width=33).grid(
            row=2, column=1, padx=(0, 14), pady=6, sticky="ew"
        )
        tk.Label(self, text="代理端口", width=13, anchor="w").grid(
            row=3, column=0, padx=(14, 4), pady=6, sticky="w"
        )
        tk.Entry(self, textvariable=self.port_var, width=33).grid(
            row=3, column=1, padx=(0, 14), pady=6, sticky="ew"
        )
        tk.Label(
            self,
            text=(
                "推荐 Clash 使用 SOCKS5（远程 DNS），默认 127.0.0.1:7891。"
                "直连模式表示本软件不主动设置代理，外部 Proxifier 仍可能接管。"
                "启用本软件代理后，请勿再用 Proxifier 重复代理 python.exe。"
            ),
            fg="#666",
            wraplength=480,
            justify="left",
        ).grid(row=4, column=0, columnspan=2, padx=14, pady=(6, 4), sticky="w")
        tk.Label(self, textvariable=self.status_var, fg="#666").grid(
            row=5, column=0, columnspan=2, padx=14, pady=4, sticky="w"
        )
        buttons = tk.Frame(self)
        buttons.grid(row=6, column=0, columnspan=2, pady=(6, 12))
        tk.Button(buttons, text="测试代理端口", command=self._test_proxy).pack(
            side="left", padx=4
        )
        tk.Button(
            buttons,
            text="保存",
            command=self._save,
            bg="#1565C0",
            fg="white",
            relief="flat",
            padx=14,
        ).pack(side="left", padx=4)
        tk.Button(buttons, text="取消", command=self.destroy, padx=10).pack(
            side="left", padx=4
        )
        self.grab_set()

    def _values(self):
        reverse_modes = {label: key for key, label in NETWORK_MODES.items()}
        mode = reverse_modes.get(self.mode_var.get(), "direct")
        host = self.host_var.get().strip() or "127.0.0.1"
        try:
            port = int(self.port_var.get().strip() or "7891")
        except ValueError:
            raise ValueError("代理端口必须是数字")
        if not 1 <= port <= 65535:
            raise ValueError("代理端口必须在 1 到 65535 之间")
        return {"mode": mode, "host": host, "port": port}

    def _test_proxy(self):
        try:
            config = self._values()
            if config["mode"] == "direct":
                self.status_var.set("当前选择直连，不需要测试代理端口。")
                return
            with socket.create_connection(
                (config["host"], config["port"]), timeout=2
            ):
                pass
            self.status_var.set("代理端口可以连接；是否能访问目标站请再运行路线检测。")
        except (OSError, ValueError) as exc:
            self.status_var.set(f"代理端口不可用：{exc}")

    def _save(self):
        try:
            config = save_network_config(self._values())
        except (OSError, ValueError) as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        if self.on_saved:
            self.on_saved(config)
        self.destroy()
