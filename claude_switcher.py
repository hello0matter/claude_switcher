import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext
import json
import os
import subprocess
import winreg
import ctypes
import threading
import time
import urllib.error
import urllib.request

CONFIG_FILE   = os.path.expanduser("~/.cc_routes.json")
SETTINGS_FILE = os.path.expanduser("~/.claude/settings.json")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_TABLE_FILE = os.path.join(APP_DIR, "model_test_tables.json")
DEFAULT_ROUTE_KEY = "__default__"

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

AI_IMPORT_PROMPT = """请帮我把中转站模型列表整理成软件可以导入的表格数据。
我会给你截图、网页复制文字或 Excel 复制内容。你只需要识别模型名、价格、渠道、标签和备注。

请只输出 JSON 数组，不要解释，不要 Markdown 代码块。每个对象字段固定为：
model, input_price, output_price, cache_read_price, cache_write_price, billing, channel, tags, note, site_note

要求：
1. 价格统一为数字，单位为 USD / 1M Tokens；如果截图是“/次”计费，把 billing 写为 per_request，并把模型价格写到 note。
2. 缺失价格填空字符串，不要猜测。
3. tags 为数组，例如 ["独家渠道","高缓存","官MAX"]。
4. note 写模型卡片里的说明，site_note 写站点特有备注。
5. 保留模型名原文，不要改名。

输出示例：
[{"model":"claude-sonnet-4-6-A","input_price":1.2,"output_price":6,"cache_read_price":0.12,"cache_write_price":1.5,"billing":"按量计费","channel":"独家渠道","tags":["高缓存"],"note":"截图里的说明","site_note":""}]
"""

DEFAULT_MODEL_ROWS = [
    {"model": "claude-haiku-4-5-20251001", "input_price": 0.8, "output_price": 4, "cache_read_price": 0.1, "cache_write_price": 1.25, "billing": "按量计费", "channel": "Claude默认渠道", "tags": [], "note": "Claude默认渠道，综合缓存，速度和性价比的好选择", "site_note": ""},
    {"model": "claude-haiku-4-5-A", "input_price": 0.4, "output_price": 2, "cache_read_price": 0.04, "cache_write_price": 0.8, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-haiku-4-5-B", "input_price": 1.5, "output_price": 7.5, "cache_read_price": "", "cache_write_price": "", "billing": "按量计费", "channel": "官转", "tags": ["官转"], "note": "Claude官方MAX转发备用渠道B，满血官转", "site_note": ""},
    {"model": "claude-opus-4-6", "input_price": 4, "output_price": 20, "cache_read_price": 0.5, "cache_write_price": 5, "billing": "按量计费", "channel": "Claude默认渠道", "tags": ["高缓存", "独家渠道", "官MAX"], "note": "Claude默认渠道，综合缓存，速度和性价比的好选择，来自Claude官方Max套餐", "site_note": ""},
    {"model": "claude-opus-4-6-A", "input_price": 2, "output_price": 10, "cache_read_price": 0.2, "cache_write_price": 2.5, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-opus-4-6-B", "input_price": 8, "output_price": 40, "cache_read_price": 1.6, "cache_write_price": 12, "billing": "按量计费", "channel": "官转", "tags": ["官转"], "note": "Claude官方MAX转发备用渠道B，满血官转，本渠道只支持Claude客户端，如需外接富转请使用G渠道", "site_note": ""},
    {"model": "claude-opus-4-6-C", "input_price": 2.8, "output_price": 14, "cache_read_price": 0.35, "cache_write_price": 3, "billing": "按量计费", "channel": "谷歌渠道", "tags": ["高缓存", "Antigravity"], "note": "谷歌渠道的满血Claude，超优惠，正常情况缓存率90%+", "site_note": ""},
    {"model": "claude-opus-4-6-F", "input_price": 4, "output_price": 20, "cache_read_price": 0.5, "cache_write_price": 5, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-6-G", "input_price": 10, "output_price": 50, "cache_read_price": 1.5, "cache_write_price": 15, "billing": "按量计费", "channel": "官转", "tags": ["官转"], "note": "官方MAX账号转发，支持1M上下文、联网搜索等原生功能，支持外接其他客户端，除了贵点没缺点", "site_note": ""},
    {"model": "claude-opus-4-6-G2", "input_price": 20, "output_price": 100, "cache_read_price": 2, "cache_write_price": 25, "billing": "按量计费", "channel": "官方API渠道", "tags": ["官方API渠道"], "note": "Claude官方API渠道，企业级稳定，5折价格，和使用官方API完全一致的体验", "site_note": ""},
    {"model": "claude-opus-4-6-T", "input_price": 1.5, "output_price": 7.5, "cache_read_price": 0.15, "cache_write_price": 1.5, "billing": "按量计费", "channel": "kiro渠道", "tags": ["kiro渠道", "无缓存"], "note": "Claude特价渠道，来自Kiro，不带缓存，速度一般，但依旧是Opus不窄小腿；如果需要缓存可以使用claude-opus-4-6-T2", "site_note": ""},
    {"model": "claude-opus-4-6-T2", "input_price": 2.5, "output_price": 12.5, "cache_read_price": 0.3, "cache_write_price": 3.6, "billing": "按量计费", "channel": "kiro渠道", "tags": ["kiro渠道", "高缓存"], "note": "Claude特价渠道，缓存率99.9%的Kiro渠道，客户端反馈营销比不带缓存的高且实际消耗比1.5/M的还低，追求性价比的可以尝试一下！", "site_note": ""},
    {"model": "claude-opus-4-6-thinking", "input_price": 5, "output_price": 25, "cache_read_price": 0.5, "cache_write_price": 6.25, "billing": "按量计费", "channel": "官转", "tags": ["输入基本不计费", "独家渠道"], "note": "强制Thinking模型，来自官转", "site_note": ""},
    {"model": "claude-opus-4-6-thinking-A", "input_price": 2, "output_price": 10, "cache_read_price": 0.2, "cache_write_price": 2.5, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-opus-4-6-Z", "input_price": "", "output_price": "", "cache_read_price": "", "cache_write_price": "", "billing": "按次计费", "channel": "", "tags": [], "note": "模型价格 $0.480 / 次", "site_note": ""},
    {"model": "claude-opus-4-6-Z2", "input_price": "", "output_price": "", "cache_read_price": "", "cache_write_price": "", "billing": "按次计费", "channel": "", "tags": [], "note": "模型价格 $0.040 / 次", "site_note": ""},
    {"model": "claude-opus-4-7", "input_price": 4, "output_price": 20, "cache_read_price": 0.5, "cache_write_price": 5, "billing": "按量计费", "channel": "Claude默认渠道", "tags": ["独家渠道", "官MAX"], "note": "Claude默认渠道，综合缓存，速度和性价比的好选择，来自Claude官方Max套餐", "site_note": ""},
    {"model": "claude-opus-4-7-A", "input_price": 2, "output_price": 10, "cache_read_price": 0.2, "cache_write_price": 2.5, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-opus-4-7-B", "input_price": 8, "output_price": 40, "cache_read_price": 0.8, "cache_write_price": 10, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-7-F", "input_price": 4, "output_price": 20, "cache_read_price": 0.5, "cache_write_price": 5, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-7-G", "input_price": 12, "output_price": 60, "cache_read_price": 1.2, "cache_write_price": 15, "billing": "按量计费", "channel": "官转", "tags": ["官转"], "note": "官方MAX账号转发，支持1M上下文、联网搜索等原生功能，支持外接其他客户端，除了贵点没缺点", "site_note": ""},
    {"model": "claude-opus-4-7-G2", "input_price": 20, "output_price": 100, "cache_read_price": 2, "cache_write_price": 25, "billing": "按量计费", "channel": "官方API渠道", "tags": ["官方API渠道"], "note": "Claude官方API渠道，企业级稳定，5折价格，和使用官方API完全一致的体验", "site_note": ""},
    {"model": "claude-opus-4-7-T", "input_price": 1.5, "output_price": 7.5, "cache_read_price": 0.15, "cache_write_price": 1.5, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-7-thinking", "input_price": 5, "output_price": 25, "cache_read_price": 0.5, "cache_write_price": 6.25, "billing": "按量计费", "channel": "官转", "tags": ["输入基本不计费"], "note": "强制Thinking模型，来自官转", "site_note": ""},
    {"model": "claude-opus-4-7-thinking-A", "input_price": 2, "output_price": 10, "cache_read_price": 0.2, "cache_write_price": 2.5, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-opus-4-8", "input_price": 4, "output_price": 20, "cache_read_price": 0.5, "cache_write_price": 5, "billing": "按量计费", "channel": "Claude默认渠道", "tags": ["高缓存", "独家渠道", "官MAX"], "note": "Claude默认渠道，综合缓存，速度和性价比的好选择，来自Claude官方Max套餐", "site_note": ""},
    {"model": "claude-opus-4-8-A", "input_price": 2, "output_price": 10, "cache_read_price": 0.2, "cache_write_price": 2.5, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-opus-4-8-B", "input_price": 8, "output_price": 40, "cache_read_price": 0.8, "cache_write_price": 10, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-8-F", "input_price": 4, "output_price": 20, "cache_read_price": 0.5, "cache_write_price": 5, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-8-G", "input_price": 12, "output_price": 60, "cache_read_price": 1.2, "cache_write_price": 15, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-8-G2", "input_price": 20, "output_price": 100, "cache_read_price": 2, "cache_write_price": 25, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-8-T", "input_price": 1.5, "output_price": 7.5, "cache_read_price": "", "cache_write_price": "", "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-opus-4-8-thinking", "input_price": 5, "output_price": 25, "cache_read_price": 0.5, "cache_write_price": 6.25, "billing": "按量计费", "channel": "官转", "tags": ["输入基本不计费", "独家渠道"], "note": "强制Thinking模型，来自官转", "site_note": ""},
    {"model": "claude-opus-4-8-thinking-A", "input_price": 2, "output_price": 10, "cache_read_price": 0.2, "cache_write_price": 2.5, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-sonnet-4-6", "input_price": 2.4, "output_price": 12, "cache_read_price": 0.3, "cache_write_price": 3, "billing": "按量计费", "channel": "Claude默认渠道", "tags": ["高缓存", "独家渠道", "官MAX"], "note": "Claude默认渠道，综合缓存，速度和性价比的好选择，来自Claude官方Max套餐", "site_note": ""},
    {"model": "claude-sonnet-4-6-A", "input_price": 1.2, "output_price": 6, "cache_read_price": 0.12, "cache_write_price": 1.5, "billing": "按量计费", "channel": "Claude独家渠道", "tags": ["独家渠道", "高缓存", "输入基本不计费"], "note": "来自谷歌/AWS-Q，Coding能力满血其他能力自测；99%缓存率实际费用比其他家0.1倍率还低。", "site_note": ""},
    {"model": "claude-sonnet-4-6-B", "input_price": 4, "output_price": 20, "cache_read_price": 0.8, "cache_write_price": 5, "billing": "按量计费", "channel": "官转", "tags": ["官转"], "note": "Claude官方MAX转发备用渠道B，满血官转，本渠道只支持Claude客户端，如果需要外接富转请使用G渠道", "site_note": ""},
    {"model": "claude-sonnet-4-6-C", "input_price": 1.7, "output_price": 8.5, "cache_read_price": 0.32, "cache_write_price": 2, "billing": "按量计费", "channel": "谷歌渠道", "tags": ["高缓存", "Antigravity"], "note": "谷歌渠道的满血Claude，超优惠，正常情况缓存率90%+", "site_note": ""},
    {"model": "claude-sonnet-4-6-F", "input_price": 2.4, "output_price": 12, "cache_read_price": 3, "cache_write_price": 3, "billing": "按量计费", "channel": "", "tags": [], "note": "", "site_note": ""},
    {"model": "claude-sonnet-4-6-G", "input_price": 6, "output_price": 30, "cache_read_price": 6, "cache_write_price": 9, "billing": "按量计费", "channel": "官转", "tags": ["官转"], "note": "官方MAX账号转发，支持1M上下文，但是贵", "site_note": ""},
    {"model": "claude-sonnet-4-6-G2", "input_price": 12, "output_price": 60, "cache_read_price": 1.2, "cache_write_price": 15, "billing": "按量计费", "channel": "官方API渠道", "tags": ["官方API渠道"], "note": "Claude官方API渠道，企业级稳定，5折价格，和使用官方API完全一致的体验", "site_note": ""},
    {"model": "claude-sonnet-4-6-T", "input_price": 0.9, "output_price": 4.5, "cache_read_price": 0.09, "cache_write_price": 0.9, "billing": "按量计费", "channel": "kiro渠道", "tags": ["kiro渠道", "无缓存"], "note": "Claude特价渠道，来自Kiro，不带缓存，速度一般，但依旧是Claude模型不窄小腿；如果需要缓存可以使用claude-sonnet-4-6-T2", "site_note": ""},
    {"model": "claude-sonnet-4-6-T2", "input_price": 1.5, "output_price": 7.5, "cache_read_price": 0.2, "cache_write_price": 2, "billing": "按量计费", "channel": "kiro渠道", "tags": ["kiro渠道", "高缓存"], "note": "Claude特价渠道，缓存率99.9%的Kiro渠道，客户端反馈营销比不带缓存的高且实际消耗比1.5/M的还低，追求性价比的可以尝试一下！", "site_note": ""},
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


def route_table_key(route):
    name = route.get("name", "").strip() or "未命名"
    base_url = route.get("base_url", "").strip()
    return f"{name}@@{base_url}"


def normalize_model_row(row):
    result = {
        "model": "",
        "input_price": "",
        "output_price": "",
        "cache_read_price": "",
        "cache_write_price": "",
        "billing": "按量计费",
        "channel": "",
        "tags": [],
        "note": "",
        "site_note": "",
        "enabled": True,
        "last_status": "",
        "last_latency_ms": "",
        "last_error": "",
        "last_tested_at": "",
    }
    result.update(row or {})
    if isinstance(result.get("tags"), str):
        result["tags"] = [x.strip() for x in result["tags"].split(",") if x.strip()]
    elif not isinstance(result.get("tags"), list):
        result["tags"] = []
    if "completion_price" in result and not result.get("output_price"):
        result["output_price"] = result.get("completion_price", "")
    return result


def load_model_tables():
    if os.path.exists(MODEL_TABLE_FILE):
        try:
            with open(MODEL_TABLE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("ai_import_prompt", AI_IMPORT_PROMPT)
            tables = data.setdefault("tables", {})
            for key, rows in list(tables.items()):
                tables[key] = [normalize_model_row(row) for row in rows]
            if DEFAULT_ROUTE_KEY not in tables:
                tables[DEFAULT_ROUTE_KEY] = [normalize_model_row(row) for row in DEFAULT_MODEL_ROWS]
            return data
        except Exception:
            pass
    return {
        "ai_import_prompt": AI_IMPORT_PROMPT,
        "tables": {DEFAULT_ROUTE_KEY: [normalize_model_row(row) for row in DEFAULT_MODEL_ROWS]},
    }


def save_model_tables(data):
    with open(MODEL_TABLE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_model_rows_for_route(route):
    data = load_model_tables()
    tables = data.setdefault("tables", {})
    key = route_table_key(route)
    if key not in tables:
        tables[key] = [normalize_model_row(row) for row in tables.get(DEFAULT_ROUTE_KEY, DEFAULT_MODEL_ROWS)]
        save_model_tables(data)
    return data, key, tables[key]


def to_float(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def price_display(value):
    number = to_float(value)
    if number is None:
        return ""
    return f"{number:g}"


def build_anthropic_messages_url(base_url):
    base = (base_url or "https://api.anthropic.com").rstrip("/")
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/v1/messages"


def test_model(route, model, timeout=30):
    api_key = route.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not api_key:
        return False, "", "缺少 API Key"

    url = build_anthropic_messages_url(route.get("base_url", ""))
    payload = {
        "model": model,
        "max_tokens": 8,
        "messages": [{"role": "user", "content": "Reply OK only."}],
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
        latency = int((time.time() - start) * 1000)
        return True, latency, body[:300]
    except urllib.error.HTTPError as exc:
        body = exc.read(2048).decode("utf-8", errors="replace")
        return False, "", f"HTTP {exc.code}: {body[:300]}"
    except Exception as exc:
        return False, "", str(exc)


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


class ModelEditor(tk.Toplevel):
    def __init__(self, parent, row=None, title="编辑模型"):
        super().__init__(parent)
        self.title(title)
        self.geometry("560x520")
        self.minsize(520, 460)
        self.result = None
        row = normalize_model_row(row or {})

        fields = [
            ("模型名 *", "model"),
            ("输入价格", "input_price"),
            ("补全/输出价格", "output_price"),
            ("缓存读取价格", "cache_read_price"),
            ("缓存创建价格", "cache_write_price"),
            ("计费方式", "billing"),
            ("渠道", "channel"),
            ("标签（逗号分隔）", "tags"),
            ("备注", "note"),
            ("站点备注", "site_note"),
        ]
        self.vars = {}
        form = tk.Frame(self)
        form.pack(fill="both", expand=True, padx=12, pady=12)
        for i, (label, key) in enumerate(fields):
            tk.Label(form, text=label, width=16, anchor="w").grid(row=i, column=0, sticky="nw", pady=4)
            value = row.get(key, "")
            if key == "tags":
                value = ", ".join(value) if isinstance(value, list) else value
            var = tk.StringVar(value=str(value))
            if key in ("note", "site_note"):
                text = tk.Text(form, height=4, width=48)
                text.insert("1.0", var.get())
                text.grid(row=i, column=1, sticky="ew", pady=4)
                self.vars[key] = text
            else:
                entry = tk.Entry(form, textvariable=var, width=50)
                entry.grid(row=i, column=1, sticky="ew", pady=4)
                self.vars[key] = var
        form.columnconfigure(1, weight=1)

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=12, pady=(0, 12))
        tk.Button(btns, text="保存", command=self._save, width=12).pack(side="right", padx=4)
        tk.Button(btns, text="取消", command=self.destroy, width=12).pack(side="right", padx=4)

        self.grab_set()
        self.wait_window()

    def _get_value(self, key):
        widget = self.vars[key]
        if isinstance(widget, tk.Text):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()

    def _save(self):
        row = {key: self._get_value(key) for key in self.vars}
        if not row["model"]:
            messagebox.showwarning("提示", "模型名不能为空", parent=self)
            return
        row["tags"] = [x.strip() for x in row.get("tags", "").split(",") if x.strip()]
        self.result = normalize_model_row(row)
        self.destroy()


class PromptEditor(tk.Toplevel):
    def __init__(self, parent, prompt):
        super().__init__(parent)
        self.title("AI 导入 Prompt")
        self.geometry("760x520")
        self.result = None
        self.text = scrolledtext.ScrolledText(self, wrap="word")
        self.text.pack(fill="both", expand=True, padx=10, pady=10)
        self.text.insert("1.0", prompt)
        btns = tk.Frame(self)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="恢复内置", command=self._reset).pack(side="left")
        tk.Button(btns, text="保存", command=self._save, width=12).pack(side="right", padx=4)
        tk.Button(btns, text="取消", command=self.destroy, width=12).pack(side="right", padx=4)
        self.grab_set()
        self.wait_window()

    def _reset(self):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", AI_IMPORT_PROMPT)

    def _save(self):
        self.result = self.text.get("1.0", "end").strip()
        self.destroy()


class AIImportDialog(tk.Toplevel):
    def __init__(self, parent, prompt):
        super().__init__(parent)
        self.title("AI 导入当前测试表格")
        self.geometry("900x720")
        self.result = None
        self.prompt_result = None

        help_text = (
            "通俗用法：\n"
            "1. 点“复制给AI的要求”，把上面那段要求发给 AI。\n"
            "2. 再把中转站的模型截图、网页文字、Excel 复制内容发给 AI。\n"
            "3. AI 会回你一段以 [ 开头、] 结尾的表格数据。\n"
            "4. 把那段数据粘到下面的大框里，点“追加导入”或“覆盖导入”。"
        )
        tk.Label(self, text=help_text, justify="left", anchor="w", fg="#444").pack(fill="x", padx=10, pady=(10, 0))

        pane = tk.PanedWindow(self, orient="vertical", sashrelief="raised")
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        prompt_frame = tk.LabelFrame(pane, text="第 1 步：复制这段要求给 AI（可以自己改）")
        self.prompt_text = scrolledtext.ScrolledText(prompt_frame, wrap="word", height=12)
        self.prompt_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.prompt_text.insert("1.0", prompt)
        pane.add(prompt_frame)

        json_frame = tk.LabelFrame(pane, text="第 2 步：把 AI 回你的表格数据粘到这里")
        self.json_text = scrolledtext.ScrolledText(json_frame, wrap="word", height=16)
        self.json_text.pack(fill="both", expand=True, padx=6, pady=6)
        pane.add(json_frame)

        btns = tk.Frame(self)
        btns.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btns, text="复制给AI的要求", command=self._copy_prompt).pack(side="left", padx=3)
        tk.Button(btns, text="只保存这段要求", command=self._save_prompt_only).pack(side="left", padx=3)
        tk.Button(btns, text="追加导入", command=lambda: self._import(False), bg="#4CAF50", fg="white").pack(side="right", padx=3)
        tk.Button(btns, text="覆盖导入", command=lambda: self._import(True)).pack(side="right", padx=3)
        tk.Button(btns, text="取消", command=self.destroy).pack(side="right", padx=3)

        self.grab_set()
        self.wait_window()

    def _copy_prompt(self):
        self.clipboard_clear()
        self.clipboard_append(self.prompt_text.get("1.0", "end").strip())
        messagebox.showinfo("已复制", "已经复制。现在把它发给 AI，再把模型截图/网页文字也发给 AI。", parent=self)

    def _save_prompt_only(self):
        self.prompt_result = self.prompt_text.get("1.0", "end").strip()
        messagebox.showinfo("完成", "Prompt 已暂存，导入或关闭后会保存", parent=self)

    def _import(self, replace):
        raw = self.json_text.get("1.0", "end").strip()
        if not raw:
            messagebox.showwarning("提示", "请先把 AI 回你的那段表格数据粘到下面的大框里", parent=self)
            return
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data.get("models") or data.get("rows") or data.get("data")
            if not isinstance(data, list):
                raise ValueError("格式不对：需要粘贴 AI 输出的完整表格数据，通常以 [ 开头、] 结尾")
            rows = [normalize_model_row(row) for row in data]
            rows = [row for row in rows if row.get("model")]
            if not rows:
                raise ValueError("没有识别到模型名字段 model")
        except Exception as exc:
            messagebox.showerror("JSON 解析失败", str(exc), parent=self)
            return
        self.prompt_result = self.prompt_text.get("1.0", "end").strip()
        self.result = {"replace": replace, "rows": rows}
        self.destroy()


class ModelTestDialog(tk.Toplevel):
    def __init__(self, parent, route):
        super().__init__(parent)
        self.parent = parent
        self.route = route
        self.data, self.table_key, self.rows = get_model_rows_for_route(route)
        self.title(f"模型测试 - {route.get('name', '')}")
        self.geometry("1120x680")
        self.minsize(980, 560)
        self.filtered_indexes = []
        self._testing = False
        self.sort_column = "model"
        self.sort_reverse = False
        self.column_headings = {}

        self.input_max_var = tk.StringVar(value="4")
        self.output_max_var = tk.StringVar(value="12")
        self.cache_max_var = tk.StringVar(value="")
        self.keyword_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="默认筛选：输入 <= 4，输出 <= 12，缓存不限")

        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        top = tk.LabelFrame(self, text="筛选与操作", padx=8, pady=6)
        top.pack(fill="x", padx=10, pady=(10, 6))

        for label, var, width in [
            ("模型/备注", self.keyword_var, 18),
            ("输入 <=", self.input_max_var, 6),
            ("输出 <=", self.output_max_var, 6),
            ("缓存 <=", self.cache_max_var, 6),
        ]:
            tk.Label(top, text=label).pack(side="left", padx=(4, 2))
            tk.Entry(top, textvariable=var, width=width).pack(side="left", padx=(0, 8))

        tk.Button(top, text="筛选", command=self._refresh_table).pack(side="left", padx=2)
        tk.Button(top, text="清空筛选", command=self._clear_filter).pack(side="left", padx=2)
        tk.Button(top, text="测试筛选结果", command=self._test_filtered, bg="#4CAF50", fg="white").pack(side="left", padx=(12, 2))
        tk.Button(top, text="测试选中", command=self._test_selected).pack(side="left", padx=2)
        tk.Button(top, text="应用模型到路线", command=self._apply_selected_model).pack(side="left", padx=2)

        mid = tk.Frame(self)
        mid.pack(fill="both", expand=True, padx=10, pady=6)
        columns = ("model", "input", "output", "cache_read", "cache_write", "channel", "tags", "status", "latency")
        self.tree = ttk.Treeview(mid, columns=columns, show="headings", selectmode="extended")
        headings = {
            "model": "模型",
            "input": "输入",
            "output": "输出/补全",
            "cache_read": "缓存读",
            "cache_write": "缓存写",
            "channel": "渠道",
            "tags": "标签",
            "status": "状态",
            "latency": "耗时ms",
        }
        self.column_headings = headings
        widths = {"model": 230, "input": 70, "output": 80, "cache_read": 70, "cache_write": 70, "channel": 110, "tags": 190, "status": 70, "latency": 70}
        for col in columns:
            self.tree.heading(col, text=headings[col], command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=widths[col], anchor="w")
        ysb = tk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        xsb = tk.Scrollbar(mid, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)
        self.tree.bind("<Double-Button-1>", lambda e: self._show_detail())

        bottom = tk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 8))
        for text, cmd in [
            ("新增", self._add_row),
            ("编辑", self._edit_row),
            ("删除", self._delete_rows),
            ("查看明细", self._show_detail),
            ("AI导入表格", self._ai_import),
            ("AI导入Prompt", self._edit_prompt),
            ("保存表格", self._save),
        ]:
            tk.Button(bottom, text=text, command=cmd).pack(side="left", padx=3)
        tk.Button(bottom, text="用内置 Claude 表重置当前站点", command=self._reset_default).pack(side="left", padx=(18, 3))
        tk.Label(bottom, textvariable=self.status_var, fg="#666").pack(side="right")

    def _row_matches(self, row):
        keyword = self.keyword_var.get().strip().lower()
        if keyword:
            haystack = " ".join([
                str(row.get("model", "")),
                str(row.get("channel", "")),
                ",".join(row.get("tags", [])),
                str(row.get("note", "")),
                str(row.get("site_note", "")),
            ]).lower()
            if keyword not in haystack:
                return False
        input_max = to_float(self.input_max_var.get())
        output_max = to_float(self.output_max_var.get())
        cache_max = to_float(self.cache_max_var.get())
        input_price = to_float(row.get("input_price"))
        output_price = to_float(row.get("output_price"))
        cache_prices = [x for x in [to_float(row.get("cache_read_price")), to_float(row.get("cache_write_price"))] if x is not None]
        if input_max is not None and (input_price is None or input_price > input_max):
            return False
        if output_max is not None and (output_price is None or output_price > output_max):
            return False
        if cache_max is not None and cache_prices and max(cache_prices) > cache_max:
            return False
        return True

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        matched_indexes = []
        for idx, row in enumerate(self.rows):
            row = normalize_model_row(row)
            self.rows[idx] = row
            if not self._row_matches(row):
                continue
            matched_indexes.append(idx)

        self.filtered_indexes = self._sorted_indexes(matched_indexes)
        self._refresh_headings()
        for idx in self.filtered_indexes:
            row = self.rows[idx]
            self.tree.insert("", "end", iid=str(idx), values=(
                row.get("model", ""),
                price_display(row.get("input_price")),
                price_display(row.get("output_price")),
                price_display(row.get("cache_read_price")),
                price_display(row.get("cache_write_price")),
                row.get("channel", ""),
                ", ".join(row.get("tags", [])),
                row.get("last_status", ""),
                row.get("last_latency_ms", ""),
            ))
        self.status_var.set(f"显示 {len(self.filtered_indexes)} / 共 {len(self.rows)} 个模型")

    def _sort_value(self, idx):
        row = self.rows[idx]
        numeric_keys = {
            "input": "input_price",
            "output": "output_price",
            "cache_read": "cache_read_price",
            "cache_write": "cache_write_price",
            "latency": "last_latency_ms",
        }
        if self.sort_column in numeric_keys:
            value = to_float(row.get(numeric_keys[self.sort_column]))
            return (value is None, value if value is not None else 0)
        if self.sort_column == "tags":
            return ", ".join(row.get("tags", [])).lower()
        if self.sort_column == "status":
            return str(row.get("last_status", "")).lower()
        if self.sort_column == "channel":
            return str(row.get("channel", "")).lower()
        return str(row.get("model", "")).lower()

    def _sorted_indexes(self, indexes):
        return sorted(indexes, key=self._sort_value, reverse=self.sort_reverse)

    def _sort_by(self, column):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        self._refresh_table()

    def _refresh_headings(self):
        for col, text in self.column_headings.items():
            arrow = ""
            if col == self.sort_column:
                arrow = " ↓" if self.sort_reverse else " ↑"
            self.tree.heading(col, text=text + arrow, command=lambda c=col: self._sort_by(c))

    def _clear_filter(self):
        self.keyword_var.set("")
        self.input_max_var.set("")
        self.output_max_var.set("")
        self.cache_max_var.set("")
        self._refresh_table()

    def _selected_indexes(self):
        return [int(iid) for iid in self.tree.selection()]

    def _add_row(self):
        editor = ModelEditor(self, title="新增模型")
        if editor.result:
            self.rows.append(editor.result)
            self._save()
            self._refresh_table()

    def _edit_row(self):
        indexes = self._selected_indexes()
        if not indexes:
            messagebox.showwarning("提示", "请先选择模型", parent=self)
            return
        idx = indexes[0]
        editor = ModelEditor(self, self.rows[idx], "编辑模型")
        if editor.result:
            merged = normalize_model_row(self.rows[idx])
            merged.update(editor.result)
            self.rows[idx] = merged
            self._save()
            self._refresh_table()

    def _delete_rows(self):
        indexes = sorted(self._selected_indexes(), reverse=True)
        if not indexes:
            return
        if not messagebox.askyesno("确认删除", f"删除选中的 {len(indexes)} 个模型？", parent=self):
            return
        for idx in indexes:
            self.rows.pop(idx)
        self._save()
        self._refresh_table()

    def _show_detail(self):
        indexes = self._selected_indexes()
        if not indexes:
            return
        row = normalize_model_row(self.rows[indexes[0]])
        detail = tk.Toplevel(self)
        detail.title(row.get("model", "模型明细"))
        detail.geometry("640x460")
        text = scrolledtext.ScrolledText(detail, wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=10)
        text.insert("1.0", json.dumps(row, ensure_ascii=False, indent=2))
        text.config(state="disabled")

    def _edit_prompt(self):
        editor = PromptEditor(self, self.data.get("ai_import_prompt", AI_IMPORT_PROMPT))
        if editor.result:
            self.data["ai_import_prompt"] = editor.result
            save_model_tables(self.data)
            messagebox.showinfo("完成", "AI 导入 Prompt 已保存", parent=self)

    def _ai_import(self):
        editor = AIImportDialog(self, self.data.get("ai_import_prompt", AI_IMPORT_PROMPT))
        if editor.prompt_result:
            self.data["ai_import_prompt"] = editor.prompt_result
        if editor.result:
            if editor.result["replace"]:
                self.rows[:] = editor.result["rows"]
            else:
                existing = {row.get("model"): i for i, row in enumerate(self.rows)}
                for row in editor.result["rows"]:
                    model = row.get("model")
                    if model in existing:
                        merged = normalize_model_row(self.rows[existing[model]])
                        merged.update(row)
                        self.rows[existing[model]] = merged
                    else:
                        self.rows.append(row)
            self._save()
            self._refresh_table()
            messagebox.showinfo("完成", "AI 表格导入完成", parent=self)
        elif editor.prompt_result:
            save_model_tables(self.data)

    def _reset_default(self):
        if not messagebox.askyesno("确认重置", "用内置 Claude 模型表覆盖当前站点表格？", parent=self):
            return
        self.rows[:] = [normalize_model_row(row) for row in DEFAULT_MODEL_ROWS]
        self._save()
        self._refresh_table()

    def _save(self):
        self.data.setdefault("tables", {})[self.table_key] = self.rows
        save_model_tables(self.data)

    def _test_selected(self):
        indexes = self._selected_indexes()
        if not indexes:
            messagebox.showwarning("提示", "请先选择模型", parent=self)
            return
        self._start_tests(indexes)

    def _test_filtered(self):
        if not self.filtered_indexes:
            messagebox.showwarning("提示", "当前筛选无模型", parent=self)
            return
        if not messagebox.askyesno("确认测试", f"将测试 {len(self.filtered_indexes)} 个模型，继续？", parent=self):
            return
        self._start_tests(list(self.filtered_indexes))

    def _start_tests(self, indexes):
        if self._testing:
            messagebox.showwarning("提示", "测试正在进行中", parent=self)
            return
        self._testing = True
        thread = threading.Thread(target=self._run_tests, args=(indexes,), daemon=True)
        thread.start()

    def _run_tests(self, indexes):
        total = len(indexes)
        for offset, idx in enumerate(indexes, 1):
            row = normalize_model_row(self.rows[idx])
            model = row.get("model", "")
            self.after(0, lambda m=model, o=offset, t=total: self.status_var.set(f"测试中 {o}/{t}: {m}"))
            ok, latency, info = test_model(self.route, model)
            row["last_status"] = "联通" if ok else "失败"
            row["last_latency_ms"] = latency
            row["last_error"] = "" if ok else info
            row["last_tested_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.rows[idx] = row
            self.after(0, self._refresh_table)
        self._save()
        self._testing = False
        self.after(0, lambda: self.status_var.set("测试完成"))

    def _apply_selected_model(self):
        indexes = self._selected_indexes()
        if not indexes:
            messagebox.showwarning("提示", "请先选择模型", parent=self)
            return
        model = self.rows[indexes[0]].get("model", "")
        self.route["model"] = model
        save_routes(self.parent.routes)
        route_idx = self.parent._selected_idx()
        self.parent._refresh_list(route_idx)
        if route_idx is not None:
            self.parent._update_detail(route_idx)
        messagebox.showinfo("完成", f"已把模型写入当前路线：{model}", parent=self)


# ── 主窗口 ────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Claude Route Switcher")
        self.geometry("820x500")
        self.minsize(680, 420)

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
        ).pack(fill="x", pady=(0, 4))

        tk.Button(
            btn_area, text="🧪  模型测试表格",
            command=self._open_model_tests,
            bg="#EF6C00", fg="white", font=("", 10, "bold"),
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

    def _open_model_tests(self):
        idx = self._selected_idx()
        if idx is None:
            messagebox.showwarning("提示", "请先选择一条路线")
            return
        ModelTestDialog(self, self.routes[idx])

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
